import grpc
import os, secrets
from concurrent import futures

from config import (
    GRPC_API_KEY, GRPC_USE_TLS, GRPC_CERT_PATH, GRPC_KEY_PATH,
    RATE_LIMIT_GRPC, RATE_LIMIT_GRPC_RECONCILE
)
from proto import receipts_pb2, receipts_pb2_grpc
from services.receipts import receipt_service
from services.reconciliation import reconcile_service
from services.security import rate_limiter
from logger import logger

def extract_peer_ip(peer_str: str) -> str:
    """Извлекает чистый IP-адрес клиента из строки peer gRPC соединения."""
    if not peer_str:
        return '127.0.0.1'
    if peer_str.startswith('ipv4:'):
        return peer_str[5:].rsplit(':', 1)[0]
    elif peer_str.startswith('ipv6:'):
        val = peer_str[5:]
        if val.startswith('[') and ']' in val:
            return val[1:val.index(']')]
        return val.rsplit(':', 1)[0]
    return peer_str.rsplit(':', 1)[0]

class AuthInterceptor(grpc.ServerInterceptor):
    """Интерцептор для проверки API-токена в метаданных gRPC запросов (Unary и Streaming)."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def intercept_service(self, continuation, handler_call_details):
        if not self._api_key:
            return continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata)
        auth_header = metadata.get('authorization', '')

        # Поддержка формата: "Bearer <token>" или просто "<token>"
        token = auth_header.split('Bearer ')[-1].strip() if 'Bearer ' in auth_header else auth_header.strip()

        if not token or not secrets.compare_digest(token, self._api_key):
            def deny_rpc(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or missing gRPC API key")
            
            # Возвращаем соответствующий обработчик в зависимости от типа RPC
            handler = continuation(handler_call_details)
            if handler and handler.unary_stream:
                return grpc.unary_stream_rpc_method_handler(deny_rpc)
            return grpc.unary_unary_rpc_method_handler(deny_rpc)

        return continuation(handler_call_details)


class RateLimitInterceptor(grpc.ServerInterceptor):
    """Интерцептор для защиты gRPC микросервиса от DoS и перегрузки (Rate Limiting)."""

    def __init__(self, default_limit: int = RATE_LIMIT_GRPC, reconcile_limit: int = RATE_LIMIT_GRPC_RECONCILE):
        self.default_limit = default_limit
        self.reconcile_limit = reconcile_limit

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        method = handler_call_details.method or ''
        is_reconcile = 'Reconcile' in method
        limit = self.reconcile_limit if is_reconcile else self.default_limit
        bucket = 'grpc_reconcile' if is_reconcile else 'grpc'

        def check_rate_limit(context):
            peer = context.peer()
            client_ip = extract_peer_ip(peer)
            allowed, retry_after, remaining = rate_limiter.is_allowed(bucket, client_ip, limit, 60)
            if not allowed:
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"Rate limit exceeded for gRPC ({bucket}). Please retry after {retry_after}s"
                )

        if handler.unary_unary:
            def wrapper(request, context):
                check_rate_limit(context)
                return handler.unary_unary(request, context)
            return grpc.unary_unary_rpc_method_handler(
                wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer
            )

        if handler.unary_stream:
            def wrapper(request, context):
                check_rate_limit(context)
                return handler.unary_stream(request, context)
            return grpc.unary_stream_rpc_method_handler(
                wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer
            )

        return handler



class ReceiptGrpcServicer(receipts_pb2_grpc.ReceiptServiceServicer):
    """gRPC реализация сервиса квитанций."""

    def GetAccount(self, request, context):
        account_number = request.account_number.strip()
        logger.debug(f"[gRPC] GetAccount: {account_number}")
        row = receipt_service.get_account(account_number)
        if not row:
            return receipts_pb2.AccountResponse(
                found=False,
                message=f"Лицевой счёт {account_number} не найден"
            )

        account = receipts_pb2.Account(
            account_number=str(row['account_number']),
            customer_name=row['customer_name'] or "",
            address=row['address'] or ""
        )
        return receipts_pb2.AccountResponse(found=True, account=account)

    def GetReceipts(self, request, context):
        account_number = request.account_number.strip()
        period_filter = request.period_filter.strip() if request.period_filter else None
        logger.debug(f"[gRPC] GetReceipts: {account_number} (период: {period_filter})")
        receipts = receipt_service.get_receipts(account_number, period_filter)

        items = []
        for r in receipts:
            items.append(receipts_pb2.ReceiptItem(
                period=r['period'] or "",
                pdf_file=r['pdf_file'] or "",
                access_token=r['access_token'] or ""
            ))

        return receipts_pb2.ReceiptsListResponse(
            account_number=account_number,
            receipts=items,
            total_count=len(items)
        )

    def GetDistinctPeriods(self, request, context):
        logger.debug("[gRPC] GetDistinctPeriods")
        periods = receipt_service.get_distinct_periods()
        period_list = [p['period'] for p in periods if p['period']]
        return receipts_pb2.PeriodsResponse(periods=period_list)

    def GetSystemStats(self, request, context):
        logger.debug("[gRPC] GetSystemStats")
        total_acc, total_rec = receipt_service.get_stats()
        return receipts_pb2.StatsResponse(
            total_accounts=total_acc,
            total_receipts=total_rec
        )

    def StreamReceiptPDF(self, request, context):
        token = request.access_token.strip()
        logger.info(f"[gRPC] StreamReceiptPDF: токен {token[:8]}...")
        fp = receipt_service.get_pdf_by_token(token)
        if not fp or not os.path.isfile(fp):
            context.abort(grpc.StatusCode.NOT_FOUND, "Квитанция не найдена по токену доступа")
            return

        chunk_size = 64 * 1024  # 64 KB chunks
        chunk_idx = 0
        file_size = os.path.getsize(fp)
        bytes_sent = 0

        with open(fp, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                bytes_sent += len(chunk)
                is_last = (bytes_sent >= file_size)
                yield receipts_pb2.FileChunk(
                    data=chunk,
                    chunk_index=chunk_idx,
                    is_last=is_last
                )
                chunk_idx += 1


class ReconcileGrpcServicer(receipts_pb2_grpc.ReconcileServiceServicer):
    """gRPC реализация сервиса аналитики и сверки."""

    def GetReconcileSummary(self, request, context):
        filt = request.filter or "without"
        period_filter = request.period_filter or ""
        page = max(1, request.page or 1)
        per_page = max(1, request.per_page or 50)
        logger.debug(f"[gRPC] GetReconcileSummary: filt={filt}, page={page}")

        data = reconcile_service.get_reconciliation_data(filt, period_filter, page, per_page)

        rows = []
        for r in data['rows']:
            has_receipt = (r['pdf_file'] is not None)
            rows.append(receipts_pb2.ReconcileRow(
                account_number=str(r['account_number'] or ""),
                customer_name=r['customer_name'] or "",
                address=r['address'] or "",
                period=r['period'] or "",
                pdf_file=r['pdf_file'] or "",
                has_receipt=has_receipt
            ))

        total_pages = max(1, (data['list_count'] + per_page - 1) // per_page)
        pct = round(data['matched'] / data['total_accounts'] * 100, 1) if data['total_accounts'] else 0.0

        return receipts_pb2.ReconcileSummaryResponse(
            total_accounts=data['total_accounts'],
            total_receipts=data['total_receipts'],
            matched=data['matched'],
            unmatched=data['unmatched'],
            orphans=data['orphans'],
            coverage_percent=float(pct),
            rows=rows,
            page=page,
            total_pages=total_pages
        )


def create_grpc_server(host: str = "0.0.0.0", port: int = 50051, max_workers: int = 10):
    """Создаёт и конфигурирует gRPC сервер с поддержкой аутентификации, Rate Limiting и TLS."""
    interceptors = []
    if GRPC_API_KEY:
        interceptors.append(AuthInterceptor(GRPC_API_KEY))
    interceptors.append(RateLimitInterceptor())

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        interceptors=interceptors
    )
    receipts_pb2_grpc.add_ReceiptServiceServicer_to_server(ReceiptGrpcServicer(), server)
    receipts_pb2_grpc.add_ReconcileServiceServicer_to_server(ReconcileGrpcServicer(), server)
    bind_addr = f"{host}:{port}"

    if GRPC_USE_TLS and GRPC_CERT_PATH and GRPC_KEY_PATH and os.path.isfile(GRPC_CERT_PATH) and os.path.isfile(GRPC_KEY_PATH):
        with open(GRPC_KEY_PATH, 'rb') as kf, open(GRPC_CERT_PATH, 'rb') as cf:
            server_credentials = grpc.ssl_server_credentials(((kf.read(), cf.read()),))
        server.add_secure_port(bind_addr, server_credentials)
        logger.info(f"gRPC микросервис запущен в защищенном режиме (TLS): {bind_addr}")
    else:
        server.add_insecure_port(bind_addr)
        logger.info(f"gRPC микросервис запущен (порт {bind_addr}, auth={'ON' if GRPC_API_KEY else 'OFF'})")

    return server


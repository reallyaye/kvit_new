"""
Пример клиентского скрипта для взаимодействия с gRPC микросервисом квитанций.
Использование: python grpc_client.py
"""
import grpc
from proto import receipts_pb2, receipts_pb2_grpc
from config import GRPC_HOST, GRPC_PORT, GRPC_API_KEY

def run():
    if not GRPC_API_KEY:
        print("❌ ОШИБКА: Переменная GRPC_API_KEY не задана в окружении или файле .env.")
        print("Укажите секретный ключ GRPC_API_KEY в файле .env перед запуском клиента.")
        return

    target = f"{'127.0.0.1' if GRPC_HOST in ('0.0.0.0', '') else GRPC_HOST}:{GRPC_PORT}"
    print(f"Подключение к gRPC серверу: {target}...")

    # Метаданные авторизации для защищённого gRPC сервера
    auth_metadata = (('authorization', f'Bearer {GRPC_API_KEY}'),)

    with grpc.insecure_channel(target) as channel:
        receipt_client = receipts_pb2_grpc.ReceiptServiceStub(channel)
        reconcile_client = receipts_pb2_grpc.ReconcileServiceStub(channel)

        print("\n1. --- Статистика системы ---")
        stats = receipt_client.GetSystemStats(receipts_pb2.EmptyRequest(), metadata=auth_metadata)
        print(f"   Лицевых счетов: {stats.total_accounts}, Всего квитанций: {stats.total_receipts}")

        print("\n2. --- Доступные периоды ---")
        periods = receipt_client.GetDistinctPeriods(receipts_pb2.EmptyRequest(), metadata=auth_metadata)
        print(f"   Периоды: {list(periods.periods)[:5]}")

        print("\n3. --- Запрос лицевого счета 800000 ---")
        account_resp = receipt_client.GetAccount(receipts_pb2.AccountRequest(account_number="800000"), metadata=auth_metadata)
        if account_resp.found:
            acc = account_resp.account
            print(f"   Найден счет: {acc.account_number} | {acc.customer_name} | {acc.address}")
        else:
            print(f"   {account_resp.message}")

        print("\n4. --- Квитанции по счету 800000 ---")
        receipts_resp = receipt_client.GetReceipts(receipts_pb2.ReceiptsQuery(account_number="800000"), metadata=auth_metadata)
        print(f"   Найдено квитанций: {receipts_resp.total_count}")
        for r in receipts_resp.receipts:
            print(f"   - Период: {r.period}, Токен: {r.access_token[:10]}..., Файл: {r.pdf_file}")

        if receipts_resp.receipts:
            token = receipts_resp.receipts[0].access_token
            print(f"\n5. --- Потоковое скачивание PDF по токену {token[:10]}... ---")
            chunks = receipt_client.StreamReceiptPDF(receipts_pb2.TokenRequest(access_token=token), metadata=auth_metadata)
            total_bytes = sum(len(c.data) for c in chunks)
            print(f"   Успешно скачано {total_bytes} байт по gRPC Stream!")

        print("\n6. --- Сверка реестра счетов ---")
        rec_resp = reconcile_client.GetReconcileSummary(
            receipts_pb2.ReconcileQuery(filter="all", page=1, per_page=5),
            metadata=auth_metadata
        )
        print(f"   Покрытие квитанциями: {rec_resp.coverage_percent}% (С квитанцией: {rec_resp.matched}, Без: {rec_resp.unmatched})")

if __name__ == '__main__':
    run()


# ==========================================
# Multi-Stage Build Dockerfile для Kvit-App
# ==========================================

# --- Этап 1: Сборка и установка зависимостей ---
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --only-binary :all: --user \
    PyMuPDF==1.25.3 \
    xlrd==2.0.1 \
    openpyxl==3.1.5 \
    grpcio>=1.83.0 \
    protobuf>=7.35.1 \
    pytest==8.3.4 \
    pytest-cov==6.0.0 \
    psycopg2-binary==2.9.10 \
    redis>=5.0.0

# --- Этап 2: Финальный легковесный образ ---
FROM python:3.11-slim AS runner

WORKDIR /app

# Установка системных зависимостей для OCR (Tesseract + словари)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-kaz \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Создаём непривилегированного пользователя appuser для безопасности
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/receipts /app/logs /app/data /app/data/spool /app/data/processing /app/data/failed && \
    chown -R appuser:appuser /app/receipts /app/logs /app/data

# Копируем установленные пакеты из builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Копируем модули и каталоги приложения
COPY --chown=appuser:appuser app.py bot.py worker.py config.py logger.py server.py import_data.py import_accounts.py set_password.py encrypt_env.py grpc_client.py ./
COPY --chown=appuser:appuser accounts_all.xlsx accounts_all.xls* ./
COPY --chown=appuser:appuser database/ ./database/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser proto/ ./proto/
COPY --chown=appuser:appuser data/ ./data/

USER appuser

# Открываем порты: 8000 (HTTP/WebSocket) и 50051 (gRPC)
EXPOSE 8000 50051

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

CMD ["python", "app.py"]

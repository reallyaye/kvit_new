# ==========================================
# Multi-Stage Build Dockerfile для Kvit-App
# ==========================================

# --- Этап 1: Сборка и установка зависимостей ---
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

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
    mkdir -p /app/receipts /app/logs /app/data && \
    chown -R appuser:appuser /app

# Копируем установленные пакеты из builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Копируем только необходимые модули и каталоги приложения (соответствие Sonar docker:S6470)
COPY --chown=appuser:appuser app.py bot.py config.py logger.py server.py import_data.py encrypt_env.py grpc_client.py ./
COPY --chown=appuser:appuser database/ ./database/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser proto/ ./proto/

USER appuser

# Открываем порты: 8000 (HTTP/WebSocket) и 50051 (gRPC)
EXPOSE 8000 50051

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

CMD ["python", "app.py"]

# Multi-stage build для оптимизации размера образа
# Stage 1: Builder - установка зависимостей
FROM python:3.11-slim as builder

WORKDIR /app

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime - финальный образ
FROM python:3.11-slim

WORKDIR /app

# Копирование установленных пакетов из builder stage
COPY --from=builder /root/.local /root/.local

# Копирование файлов приложения
COPY main.py .
COPY templates/ ./templates/
COPY static/ ./static/

# Добавление локальных пакетов в PATH
ENV PATH=/root/.local/bin:$PATH

# Переменные окружения
ENV REDIS_HOST=localhost
ENV REDIS_PORT=6379
ENV PYTHONUNBUFFERED=1

# Открытие порта
EXPOSE 8888

# Запуск приложения
CMD ["python", "main.py"]

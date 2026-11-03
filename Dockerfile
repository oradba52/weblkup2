# ── Stage 1: сборка зависимостей ──────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Системные библиотеки для сборки (bcrypt, reportlab, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libjpeg-dev zlib1g-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Только runtime-библиотеки (без build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные пакеты из builder
COPY --from=builder /install /usr/local

# Копируем код приложения
COPY gym_rental/ .

# Создаём директории для загрузок и статики
RUN mkdir -p app/uploads app/static

# Переменные окружения по умолчанию
ENV DATABASE_URL=sqlite:///./gym_rental.db \
    SECRET_KEY=change-me-in-production \
    UPLOAD_DIR=app/uploads \
    MAX_UPLOAD_MB=5 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Запускаем миграции, seed-админ и сервер
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.create_admin && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

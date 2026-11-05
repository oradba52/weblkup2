# GymRental — система учёта проката и продажи купальников

Веб-приложение на **FastAPI + Jinja2 (SSR)** с интерфейсом **AdminLTE 3**.
Управление каталогом, заказчиками, бронированиями и продажами с генерацией
отчётов и экспортом в Excel/PDF.

## Возможности

### Авторизация
- Вход по логину/паролю (bcrypt)
- Cookie-сессии с подписью (itsdangerous)
- CSRF-защита на всех формах
- Логирование всех попыток входа

### Каталог товаров
- CRUD с загрузкой фотографий (JPG, PNG, WebP до 5 МБ)
- Фильтры: по названию, размеру, типу (прокат/продажа)
- Пагинация по 20 записей
- Автоматический статус: свободен / забронирован / продан

### Заказчики
- CRUD с полями: ФИО, телефон, Telegram ID
- Поиск по имени и телефону
- Подсчёт бронирований и покупок для каждого заказчика
- Защита от удаления при наличии связанных данных

### Бронирования
- CRUD с выбором товара и заказчика
- Автоматический расчёт стоимости: цена товара × дней
- Контроль занятости: нельзя забронировать товар на занятые даты
- Статусы: активна / возвращена / отменена
- Фактическая дата возврата

### Продажи
- CRUD только для товаров типа «Продажа»
- Автоматическая отметка товара как проданного
- При удалении продажи товар возвращается в свободные
- Журнал с датой, товаром и заказчиком

### Отчёты (6 штук)
| # | Отчёт | Описание | Фильтры |
|---|-------|----------|---------|
| 1 | Остатки на складе | Группировка по размеру и типу | — |
| 2 | Выручка за период | Продажи + прокат, с итогом | Дата С / По |
| 3 | История бронирований | Полная таблица со статусами | Дата, статус |
| 4 | Просроченные брони | Активные брони с прошедшей датой | — |
| 5 | ТОП заказчиков | Выручка по продажам и прокату | Дата С / По |
| 6 | Журнал продаж | Детализация продаж | Дата С / По |

Каждый отчёт экспортируется в **Excel** (openpyxl) и **PDF** (reportlab).

## Технологии

| Слой | Технология |
|------|-----------|
| Backend | FastAPI 0.115, SQLAlchemy 2.0, Pydantic 2.10 |
| Database | SQLite (локально и в Docker) |
| Migrations | Alembic 1.14 |
| Auth | bcrypt, itsdangerous |
| Templates | Jinja2, AdminLTE 3.2, Bootstrap 4.6 |
| Reports | openpyxl (Excel), reportlab (PDF) |
| Deploy | Docker, docker-compose, Nginx |
| CI/CD | GitHub Actions |

## Запуск локально (без Docker)

### Требования
- Python 3.13+
- SQLite (встроена в Python)

### Шаги

```bash
cd gym_rental

# 1. Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Настроить окружение
cp .env.example .env
# Отредактировать .env (SECRET_KEY, ADMIN_PASSWORD и т.д.)

# 4. Применить миграции БД
alembic upgrade head

# 5. Создать администратора (из .env)
python -m scripts.create_admin

# 6. Запустить сервер
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Открыть http://localhost:8000 — редирект на страницу входа.

Данные по умолчанию: `admin / admin123` (изменить в `.env`).

## Запуск в Docker

### Требования
- Docker 24+
- Docker Compose v2+

### Шаги

```bash
# 1. Создать .env в корне проекта (опционально)
cat > .env <<EOF
SECRET_KEY=your-random-secret-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-now
HTTP_PORT=80
EOF

# 2. Собрать и запустить
docker compose up -d --build

# 3. Проверить статус
docker compose ps
```

Сервисы:
- **nginx** — http://localhost (порт настраивается через `HTTP_PORT`)
- **app** — FastAPI (внутренний порт 8000) + SQLite

База данных SQLite хранится в Docker volume `db_data` (путь `/data/gym_rental.db` внутри контейнера), поэтому данные не теряются при перезапуске.

При первом запуске автоматически:
- Применяются миграции Alembic
- Создаётся администратор из переменных окружения

### Логи

```bash
docker compose logs -f app
docker compose logs -f nginx
```

### Остановка

```bash
docker compose down
# С удалением данных БД:
docker compose down -v
```

## Миграции базы данных

Для управления схемой БД используется **Alembic**. Миграции хранятся в `gym_rental/alembic/versions/`.

### Как это работает

- `alembic/env.py` читает `DATABASE_URL` из настроек приложения и связывает миграции с моделями SQLAlchemy.
- Каждая миграция — Python-файл с функциями `upgrade()` (применить) и `downgrade()` (откатить).
- В файле `0001_initial.py` создаются все таблицы (users, login_log, person, catalog, booking, sale) и индексы.
- При запуске Docker-контейнера миграции применяются автоматически (`alembic upgrade head` в CMD).

### Команды

```bash
cd gym_rental

# Применить все миграции (создать/обновить таблицы)
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Показать текущую версию
alembic current

# Показать историю миграций
alembic history

# Создать новую миграцию после изменения моделей
alembic revision --autogenerate -m "описание изменений"
```

### Автоматический запуск

В Docker-контейнере миграции выполняются при каждом старте — команда в `Dockerfile`:
```
alembic upgrade head && python -m scripts.create_admin && uvicorn app.main:app
```
Это безопасно: если миграции уже применены, Alembic пропускает их без ошибок.

## Структура проекта

```
.
├── Dockerfile                    # Многоэтапная сборка Python-образа
├── docker-compose.yml            # app + SQLite (volume) + nginx
├── nginx/
│   └── gym_rental.conf           # Конфигурация nginx reverse-proxy
├── .github/
│   └── workflows/
│       └── app.yml              # CI/CD: lint, build, Docker push, deploy
├── gym_rental/
│   ├── alembic/                  # Миграции БД
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial.py  # Все таблицы + индексы
│   ├── app/
│   │   ├── main.py              # FastAPI приложение, middleware, дашборд
│   │   ├── config.py            # Настройки (pydantic-settings)
│   │   ├── database.py          # SQLAlchemy engine + session
│   │   ├── models/              # Модели (User, Person, Catalog, Booking, Sale, LoginLog)
│   │   ├── schemas/             # Pydantic-валидация форм
│   │   ├── routers/             # Роутеры (auth, catalog, persons, bookings, sales, reports)
│   │   ├── services/            # auth_service, upload_service
│   │   └── templates/           # Jinja2-шаблоны (base.html + страницы)
│   ├── scripts/
│   │   └── create_admin.py      # Seed-скрипт для администратора
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

## Конфигурация

Переменные окружения (файл `.env` или `docker-compose.yml`):

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `APP_NAME` | GymRental | Название приложения |
| `SECRET_KEY` | change-me-... | Ключ для подписи сессий |
| `DATABASE_URL` | sqlite:///./gym_rental.db | URL базы данных (в Docker: `sqlite:////data/gym_rental.db`) |
| `ADMIN_USERNAME` | admin | Логин администратора |
| `ADMIN_PASSWORD` | admin123 | Пароль администратора |
| `MAX_UPLOAD_MB` | 5 | Макс. размер загружаемой фотографии |
| `UPLOAD_DIR` | app/uploads | Директория для загруженных файлов |
| `SESSION_COOKIE_NAME` | gym_rental_session | Имя cookie сессии |
| `SESSION_MAX_AGE` | 86400 | Время жизни сессии (сек) |
| `HTTP_PORT` | 80 | Внешний порт nginx (для Docker) |

## CI/CD

GitHub Actions (`.github/workflows/app.yml`):

1. **frontend** — сборка фронтенда (npm ci, lint, build)
2. **backend** — проверка Python (py_compile, seed-админ)
3. **docker** — сборка и публикация образа в GitHub Container Registry
4. **deploy** — копирование compose-файлов на сервер и `docker compose up`

Для деплоя задайте секреты в GitHub:
- `DEPLOY_HOST` — IP/домен сервера
- `DEPLOY_USER` — SSH-пользователь
- `DEPLOY_SSH_KEY` — приватный SSH-ключ

## Безопасность

- Пароли хешируются bcrypt
- Cookie сессий подписаны itsdangerous (httponly, samesite=lax)
- CSRF-токены на всех POST-формах
- Auth middleware защищает все маршруты кроме /login и статики
- Загрузка файлов: проверка MIME-типа + расширения, UUID-имена, лимит размера
- Удаление заказчика блокируется при наличии связанных данных
- Удаление товара каскадно удаляет связанные брони и продажи (ON DELETE CASCADE)

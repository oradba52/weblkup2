"""FastAPI приложение — монолит с SSR (Jinja2 + AdminLTE).

Этап 1: БД + модели + Alembic + seed-админ + авторизация + логи.
"""

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import os

from app.config import settings
from app.database import SessionLocal, engine, Base
from app.routers import auth
from app.routers.auth import get_current_user

app = FastAPI(title=settings.app_name)

# Middleware для сессий (нужно для CSRF-токенов)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Шаблоны Jinja2
templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

# Статика (AdminLTE свои стили + загруженные картинки)
os.makedirs("app/static", exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Подключаем роутер авторизации
app.include_router(auth.router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Защищает все маршруты кроме /login и статических файлов."""
    path = request.url.path

    # Разрешённые пути без авторизации
    public_paths = ["/login", "/static", "/uploads"]
    if path == "/" or any(path.startswith(p) for p in public_paths):
        return await call_next(request)

    # Проверяем авторизацию
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
    finally:
        db.close()

    return await call_next(request)


@app.get("/")
async def root():
    """Корневой маршрут — редирект на /admin."""
    return RedirectResponse(url="/admin", status_code=303)


@app.get("/admin")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Дашборд — сводка (заглушка для этапа 1)."""
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "dashboard",
        },
    )


@app.get("/admin/catalog")
async def catalog_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "catalog",
         "title": "Каталог", "message": "Каталог будет реализован в следующем этапе."},
    )


@app.get("/admin/persons")
async def persons_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "persons",
         "title": "Заказчики", "message": "Заказчики будут реализованы в следующем этапе."},
    )


@app.get("/admin/bookings")
async def bookings_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "bookings",
         "title": "Бронирования", "message": "Бронирования будут реализованы в следующем этапе."},
    )


@app.get("/admin/sales")
async def sales_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "sales",
         "title": "Продажи", "message": "Продажи будут реализованы в следующем этапе."},
    )


@app.get("/admin/reports")
async def reports_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "title": "Отчёты", "message": "Отчёты будут реализованы в следующем этапе."},
    )


@app.get("/admin/users")
async def users_stub(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "stub.html",
        {"request": request, "current_user": user, "active_page": "users",
         "title": "Админы", "message": "Управление админами будет реализовано в следующем этапе."},
    )


@app.get("/admin/login-log")
async def login_log(request: Request, db: Session = Depends(get_db)):
    """Логи входов — реализуем уже на этапе 1."""
    from app.models.login_log import LoginLog
    user = get_current_user(request, db)
    logs = db.query(LoginLog).order_by(LoginLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse(
        "login_log/list.html",
        {"request": request, "current_user": user, "active_page": "login_log",
         "logs": logs},
    )

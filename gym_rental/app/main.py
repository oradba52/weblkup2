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
from app.routers import auth, admin_catalog, admin_persons, admin_bookings, admin_sales
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

# Подключаем роутеры
app.include_router(auth.router)
app.include_router(admin_catalog.router)
app.include_router(admin_persons.router)
app.include_router(admin_bookings.router)
app.include_router(admin_sales.router)


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
    """Дашборд — сводка по каталогу, бронированиям и продажам."""
    from app.models.catalog import Catalog
    from app.models.booking import Booking
    from app.models.sale import Sale
    from app.models.person import Person
    from datetime import date

    user = get_current_user(request, db)

    total_catalog = db.query(Catalog).count()
    total_rent = db.query(Catalog).filter(Catalog.type == "rent").count()
    total_sale = db.query(Catalog).filter(Catalog.type == "sale").count()
    sold_count = db.query(Catalog).filter(Catalog.is_sold == True).count()
    free_count = total_catalog - sold_count
    total_persons = db.query(Person).count()

    today = date.today()
    active_bookings = (
        db.query(Booking)
        .filter(
            Booking.status.in_(["active", "returned"]),
            Booking.data_start <= today,
            Booking.data_finish >= today,
        )
        .count()
    )

    # Продажи за текущий месяц
    month_start = date(today.year, today.month, 1)
    sales_this_month = (
        db.query(Sale).filter(Sale.sale_date >= month_start).count()
    )
    revenue_this_month = (
        db.query(Sale).filter(Sale.sale_date >= month_start)
        .with_entities(Sale.price)
        .all()
    )
    revenue_total = sum(s[0] for s in revenue_this_month) if revenue_this_month else 0.0

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "dashboard",
            "total_catalog": total_catalog,
            "total_rent": total_rent,
            "total_sale": total_sale,
            "sold_count": sold_count,
            "free_count": free_count,
            "total_persons": total_persons,
            "active_bookings": active_bookings,
            "sales_this_month": sales_this_month,
            "revenue_this_month": revenue_total,
        },
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

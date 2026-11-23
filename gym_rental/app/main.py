"""FastAPI приложение — монолит с SSR (Jinja2 + AdminLTE)."""

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import mimetypes
import os

from app.config import settings
from app.database import SessionLocal
from app.routers import auth, admin_catalog, admin_persons, admin_bookings, admin_sales, admin_reports
from app.routers.auth import get_current_user

app = FastAPI(title=settings.app_name)

# Сессия для CSRF. Secure включается настройкой только при работе через HTTPS.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)

templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

os.makedirs("app/static", exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(admin_catalog.router)
app.include_router(admin_persons.router)
app.include_router(admin_bookings.router)
app.include_router(admin_sales.router)
app.include_router(admin_reports.router)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Защищает все маршруты приложения, кроме входа и публичной статики."""
    path = request.url.path
    is_public_static = path == "/static" or path.startswith("/static/")

    if path == "/" or path == "/login" or path.startswith("/login/") or is_public_static:
        return await call_next(request)

    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        if user.role != "admin":
            return PlainTextResponse("Доступ запрещён", status_code=403)
    finally:
        db.close()

    return await call_next(request)


@app.get("/uploads/{file_path:path}")
async def serve_uploaded_file(request: Request, file_path: str):
    """Отдаёт фотографии только авторизованным пользователям."""
    relative_path = Path(file_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise HTTPException(status_code=404, detail="Файл не найден")

    upload_root = Path(settings.upload_dir).resolve()
    file_path_resolved = (upload_root / relative_path).resolve()
    if not file_path_resolved.is_relative_to(upload_root) or not file_path_resolved.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    media_type, _ = mimetypes.guess_type(file_path_resolved.name)
    return FileResponse(
        file_path_resolved,
        media_type=media_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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

    month_start = date(today.year, today.month, 1)
    sales_this_month = db.query(Sale).filter(Sale.sale_date >= month_start).count()
    revenue_this_month = (
        db.query(Sale).filter(Sale.sale_date >= month_start)
        .with_entities(Sale.price)
        .all()
    )
    revenue_total = sum(s[0] for s in revenue_this_month) if revenue_this_month else 0.0

    overdue_bookings = db.query(Booking).filter(
        Booking.status == "active",
        Booking.data_finish < today,
    ).count()

    recent_bookings = db.query(Booking).order_by(Booking.id.desc()).limit(5).all()
    recent_sales = db.query(Sale).order_by(Sale.id.desc()).limit(5).all()

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
            "overdue_bookings": overdue_bookings,
            "sales_this_month": sales_this_month,
            "revenue_this_month": revenue_total,
            "recent_bookings": recent_bookings,
            "recent_sales": recent_sales,
        },
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
    """Логи входов."""
    from app.models.login_log import LoginLog
    user = get_current_user(request, db)
    logs = db.query(LoginLog).order_by(LoginLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse(
        "login_log/list.html",
        {"request": request, "current_user": user, "active_page": "login_log",
         "logs": logs},
    )

"""Router каталога: /admin/catalog

- Список с пагинацией, фильтром по size/type, поиском по name
- CRUD: создание, редактирование, удаление
- Загрузка картинки с локальной машины
- Отображение статуса: свободен / забронирован / продан
"""

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date
import os

from app.database import SessionLocal
from app.models.catalog import Catalog
from app.models.booking import Booking
from app.routers.auth import get_current_user, generate_csrf_token, verify_csrf_token
from app.services.upload_service import save_upload, delete_file
from app.schemas.catalog import CatalogCreateForm, CatalogUpdateForm

router = APIRouter(prefix="/admin/catalog")

# Количество товаров на странице
PER_PAGE = 20


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_item_status(item: Catalog, db: Session) -> str:
    """Определяет статус товара: sold / booked / free."""
    if item.is_sold:
        return "sold"
    today = date.today()
    active_booking = (
        db.query(Booking)
        .filter(
            Booking.catalog_id == item.id,
            Booking.status.in_(["active", "returned"]),
            Booking.data_start <= today,
            Booking.data_finish >= today,
        )
        .first()
    )
    if active_booking:
        return "booked"
    return "free"


STATUS_LABELS = {
    "free": ("свободен", "success"),
    "booked": ("забронирован", "warning"),
    "sold": ("продан", "danger"),
}


@router.get("", response_class=HTMLResponse)
async def catalog_list(
    request: Request,
    page: int = Query(1, ge=1),
    size: int | None = Query(None),
    type: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Список товаров с пагинацией и фильтрами."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    query = db.query(Catalog)

    # Фильтр по размеру
    if size is not None:
        query = query.filter(Catalog.size == size)

    # Фильтр по типу
    if type and type in ("rent", "sale"):
        query = query.filter(Catalog.type == type)

    # Поиск по названию
    if search:
        query = query.filter(Catalog.name.ilike(f"%{search}%"))

    total = query.count()
    items = (
        query.order_by(Catalog.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    # Добавляем статус каждому товару
    items_with_status = []
    for item in items:
        status = get_item_status(item, db)
        label, badge = STATUS_LABELS[status]
        items_with_status.append({
            "item": item,
            "status": status,
            "status_label": label,
            "status_badge": badge,
        })

    total_pages = (total + PER_PAGE - 1) // PER_PAGE

    return request.app.state.templates.TemplateResponse(
        "catalog/list.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "catalog",
            "items": items_with_status,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "filters": {"size": size, "type": type, "search": search},
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def catalog_new(request: Request, db: Session = Depends(get_db)):
    """Форма создания нового товара."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        "catalog/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "catalog",
            "csrf_token": csrf_token,
            "item": None,
            "errors": None,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def catalog_create(
    request: Request,
    name: str = Form(...),
    size: int = Form(...),
    price: float = Form(...),
    type: str = Form(...),
    is_sold: str = Form("0"),
    image: UploadFile = File(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Обработка создания товара с загрузкой картинки."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    # Валидация
    errors = []
    if not name or len(name) > 200:
        errors.append("Название обязательно (до 200 символов)")
    if size < 20 or size > 60:
        errors.append("Размер должен быть от 20 до 60")
    if price <= 0:
        errors.append("Цена должна быть больше 0")
    if type not in ("rent", "sale"):
        errors.append("Тип должен быть rent или sale")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "catalog/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "catalog",
                "csrf_token": csrf_token,
                "item": None,
                "errors": errors,
            },
            status_code=400,
        )

    # Загрузка картинки
    try:
        rel_path = await save_upload(image)
    except HTTPException as e:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "catalog/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "catalog",
                "csrf_token": csrf_token,
                "item": None,
                "errors": [e.detail],
            },
            status_code=400,
        )

    # Создаём товар
    item = Catalog(
        name=name,
        size=size,
        price=price,
        type=type,
        path=rel_path,
        is_sold=(is_sold == "1"),
    )
    db.add(item)
    db.commit()

    return RedirectResponse(url="/admin/catalog", status_code=303)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
async def catalog_edit(request: Request, item_id: int, db: Session = Depends(get_db)):
    """Форма редактирования товара."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    item = db.query(Catalog).filter(Catalog.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    csrf_token = generate_csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        "catalog/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "catalog",
            "csrf_token": csrf_token,
            "item": item,
            "errors": None,
        },
    )


@router.post("/{item_id}/edit", response_class=HTMLResponse)
async def catalog_update(
    request: Request,
    item_id: int,
    name: str = Form(...),
    size: int = Form(...),
    price: float = Form(...),
    type: str = Form(...),
    is_sold: str = Form("0"),
    image: UploadFile | None = File(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Обработка редактирования товара."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    item = db.query(Catalog).filter(Catalog.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Валидация
    errors = []
    if not name or len(name) > 200:
        errors.append("Название обязательно (до 200 символов)")
    if size < 20 or size > 60:
        errors.append("Размер должен быть от 20 до 60")
    if price <= 0:
        errors.append("Цена должна быть больше 0")
    if type not in ("rent", "sale"):
        errors.append("Тип должен быть rent или sale")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "catalog/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "catalog",
                "csrf_token": csrf_token,
                "item": item,
                "errors": errors,
            },
            status_code=400,
        )

    # Если загружена новая картинка — сохраняем, старую удаляем
    if image and image.filename:
        try:
            rel_path = await save_upload(image)
            # Удаляем старую картинку
            if item.path:
                delete_file(item.path)
            item.path = rel_path
        except HTTPException as e:
            csrf_token = generate_csrf_token(request)
            return request.app.state.templates.TemplateResponse(
                "catalog/form.html",
                {
                    "request": request,
                    "current_user": user,
                    "active_page": "catalog",
                    "csrf_token": csrf_token,
                    "item": item,
                    "errors": [e.detail],
                },
                status_code=400,
            )

    item.name = name
    item.size = size
    item.price = price
    item.type = type
    item.is_sold = (is_sold == "1")
    db.commit()

    return RedirectResponse(url="/admin/catalog", status_code=303)


@router.post("/{item_id}/delete")
async def catalog_delete(
    request: Request,
    item_id: int,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Удаление товара."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    item = db.query(Catalog).filter(Catalog.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Удаляем картинку с диска
    if item.path:
        delete_file(item.path)

    db.delete(item)
    db.commit()

    return RedirectResponse(url="/admin/catalog", status_code=303)

"""Router бронирований: /admin/bookings

- Список с пагинацией, фильтром по статусу/датам
- CRUD: создание, редактирование, удаление
- Расчёт стоимости по цене товара и количеству дней
- Управление статусом: active / returned / cancelled
- Проверка занятости товара на выбранные даты
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date, datetime

from app.database import SessionLocal
from app.models.catalog import Catalog
from app.models.person import Person
from app.models.booking import Booking
from app.routers.auth import get_current_user, generate_csrf_token, verify_csrf_token

router = APIRouter(prefix="/admin/bookings")

PER_PAGE = 20

STATUS_LABELS = {
    "active": ("активна", "success"),
    "returned": ("возвращена", "info"),
    "cancelled": ("отменена", "secondary"),
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def calculate_price(catalog: Catalog, data_start: date, data_finish: date) -> float:
    """Стоимость = цена товара × количество дней."""
    days = (data_finish - data_start).days + 1
    return round(catalog.price * max(days, 1), 2)


def has_overlapping_booking(
    db: Session, catalog_id: int, data_start: date, data_finish: date, exclude_id: int | None = None
) -> Booking | None:
    """Проверяет, есть ли пересечение с существующей активной бронью."""
    query = db.query(Booking).filter(
        Booking.catalog_id == catalog_id,
        Booking.status == "active",
        Booking.data_start <= data_finish,
        Booking.data_finish >= data_start,
    )
    if exclude_id is not None:
        query = query.filter(Booking.id != exclude_id)
    return query.first()


def full_name(p: Person) -> str:
    parts = [p.last_name, p.first_name]
    if p.second_name:
        parts.append(p.second_name)
    return " ".join(parts)


@router.get("", response_class=HTMLResponse)
async def booking_list(
    request: Request,
    page: int = Query(1, ge=1),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)

    query = db.query(Booking)

    if status and status in ("active", "returned", "cancelled"):
        query = query.filter(Booking.status == status)

    total = query.count()
    bookings = (
        query.order_by(Booking.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    total_pages = (total + PER_PAGE - 1) // PER_PAGE

    return request.app.state.templates.TemplateResponse(
        "booking/list.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "bookings",
            "csrf_token": csrf_token,
            "bookings": bookings,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "status_filter": status,
            "status_labels": STATUS_LABELS,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def booking_new(
    request: Request,
    catalog_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)

    catalog_items = db.query(Catalog).filter(Catalog.is_sold == False).order_by(Catalog.name).all()
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()

    return request.app.state.templates.TemplateResponse(
        "booking/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "bookings",
            "csrf_token": csrf_token,
            "booking": None,
            "catalog_items": catalog_items,
            "persons": persons,
            "errors": None,
            "selected_catalog_id": catalog_id,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def booking_create(
    request: Request,
    catalog_id: str = Form(...),
    person_id: str = Form(...),
    data_start: str = Form(...),
    data_finish: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    catalog_items = db.query(Catalog).filter(Catalog.is_sold == False).order_by(Catalog.name).all()
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()

    errors = []

    try:
        cat_id = int(catalog_id)
    except (ValueError, TypeError):
        cat_id = 0
        errors.append("Выберите товар")

    try:
        per_id = int(person_id)
    except (ValueError, TypeError):
        per_id = 0
        errors.append("Выберите заказчика")

    try:
        d_start = date.fromisoformat(data_start)
    except ValueError:
        d_start = None
        errors.append("Неверный формат даты начала")

    try:
        d_finish = date.fromisoformat(data_finish)
    except ValueError:
        d_finish = None
        errors.append("Неверный формат даты окончания")

    catalog_item = db.query(Catalog).filter(Catalog.id == cat_id).first() if cat_id else None
    person = db.query(Person).filter(Person.id == per_id).first() if per_id else None

    if catalog_item is None:
        errors.append("Товар не найден")
    elif catalog_item.is_sold:
        errors.append("Товар уже продан, его нельзя забронировать")

    if person is None:
        errors.append("Заказчик не найден")

    if d_start and d_finish and d_finish < d_start:
        errors.append("Дата окончания не может быть раньше даты начала")

    if catalog_item and d_start and d_finish:
        overlap = has_overlapping_booking(db, catalog_item.id, d_start, d_finish)
        if overlap:
            errors.append(
                f"Товар уже забронирован на этот период (бронь #{overlap.id}: "
                f"{overlap.data_start} — {overlap.data_finish})"
            )

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "booking/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "bookings",
                "csrf_token": csrf_token,
                "booking": None,
                "catalog_items": catalog_items,
                "persons": persons,
                "errors": errors,
                "selected_catalog_id": cat_id if cat_id else None,
            },
            status_code=400,
        )

    total_price = calculate_price(catalog_item, d_start, d_finish)

    booking = Booking(
        catalog_id=catalog_item.id,
        person_id=person.id,
        data_start=d_start,
        data_finish=d_finish,
        total_price=total_price,
        status="active",
    )
    db.add(booking)
    db.commit()

    return RedirectResponse(url="/admin/bookings", status_code=303)


@router.get("/{booking_id}/edit", response_class=HTMLResponse)
async def booking_edit(request: Request, booking_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")

    csrf_token = generate_csrf_token(request)
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()
    catalog_item = db.query(Catalog).filter(Catalog.id == booking.catalog_id).first()

    return request.app.state.templates.TemplateResponse(
        "booking/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "bookings",
            "csrf_token": csrf_token,
            "booking": booking,
            "catalog_items": [catalog_item] if catalog_item else [],
            "persons": persons,
            "errors": None,
            "status_labels": STATUS_LABELS,
        },
    )


@router.post("/{booking_id}/edit", response_class=HTMLResponse)
async def booking_update(
    request: Request,
    booking_id: int,
    person_id: str = Form(...),
    data_start: str = Form(...),
    data_finish: str = Form(...),
    status: str = Form(...),
    fact_finish: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")

    catalog_item = db.query(Catalog).filter(Catalog.id == booking.catalog_id).first()
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()

    errors = []

    try:
        per_id = int(person_id)
    except (ValueError, TypeError):
        per_id = 0
        errors.append("Выберите заказчика")

    person = db.query(Person).filter(Person.id == per_id).first() if per_id else None
    if person is None:
        errors.append("Заказчик не найден")

    try:
        d_start = date.fromisoformat(data_start)
    except ValueError:
        d_start = None
        errors.append("Неверный формат даты начала")

    try:
        d_finish = date.fromisoformat(data_finish)
    except ValueError:
        d_finish = None
        errors.append("Неверный формат даты окончания")

    if status not in ("active", "returned", "cancelled"):
        errors.append("Недопустимый статус")

    d_fact: date | None = None
    if fact_finish and fact_finish.strip():
        try:
            d_fact = date.fromisoformat(fact_finish)
        except ValueError:
            errors.append("Неверный формат фактической даты возврата")

    if d_start and d_finish and d_finish < d_start:
        errors.append("Дата окончания не может быть раньше даты начала")

    # Проверка пересечения только если бронь активна
    if catalog_item and d_start and d_finish and status == "active":
        overlap = has_overlapping_booking(db, catalog_item.id, d_start, d_finish, exclude_id=booking.id)
        if overlap:
            errors.append(
                f"Товар уже забронирован на этот период (бронь #{overlap.id})"
            )

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "booking/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "bookings",
                "csrf_token": csrf_token,
                "booking": booking,
                "catalog_items": [catalog_item] if catalog_item else [],
                "persons": persons,
                "errors": errors,
                "status_labels": STATUS_LABELS,
            },
            status_code=400,
        )

    booking.person_id = per_id
    booking.data_start = d_start
    booking.data_finish = d_finish
    booking.fact_finish = d_fact
    booking.status = status
    booking.total_price = calculate_price(catalog_item, d_start, d_finish)
    db.commit()

    return RedirectResponse(url="/admin/bookings", status_code=303)


@router.post("/{booking_id}/delete")
async def booking_delete(
    request: Request,
    booking_id: int,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")

    db.delete(booking)
    db.commit()

    return RedirectResponse(url="/admin/bookings", status_code=303)
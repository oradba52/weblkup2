"""Router заказчиков: /admin/persons

- Список с пагинацией, поиском по имени/телефону
- CRUD: создание, редактирование, удаление
- Показ количества бронирований и продаж каждого заказчика
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
import os

from app.database import SessionLocal
from app.models.person import Person
from app.models.booking import Booking
from app.models.sale import Sale
from app.routers.auth import get_current_user, generate_csrf_token, verify_csrf_token

router = APIRouter(prefix="/admin/persons")

PER_PAGE = 20


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def full_name(p: Person) -> str:
    parts = [p.last_name, p.first_name]
    if p.second_name:
        parts.append(p.second_name)
    return " ".join(parts)


@router.get("", response_class=HTMLResponse)
async def person_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Список заказчиков с пагинацией и поиском."""
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)

    query = db.query(Person)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Person.first_name.ilike(like),
                Person.last_name.ilike(like),
                Person.second_name.ilike(like),
                Person.phone.ilike(like),
            )
        )

    total = query.count()
    persons = (
        query.order_by(Person.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    # Подсчёт бронирований и продаж
    persons_data = []
    for p in persons:
        booking_count = db.query(func.count(Booking.id)).filter(Booking.person_id == p.id).scalar() or 0
        sale_count = db.query(func.count(Sale.id)).filter(Sale.person_id == p.id).scalar() or 0
        persons_data.append({
            "person": p,
            "full_name": full_name(p),
            "booking_count": booking_count,
            "sale_count": sale_count,
        })

    total_pages = (total + PER_PAGE - 1) // PER_PAGE

    return request.app.state.templates.TemplateResponse(
        "person/list.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "persons",
            "csrf_token": csrf_token,
            "persons_data": persons_data,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "search": search,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def person_new(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        "person/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "persons",
            "csrf_token": csrf_token,
            "person": None,
            "errors": None,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def person_create(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    second_name: str = Form(""),
    phone: str = Form(...),
    telegram_id: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    errors = []
    if not first_name or len(first_name) > 100:
        errors.append("Имя обязательно (до 100 символов)")
    if not last_name or len(last_name) > 100:
        errors.append("Фамилия обязательна (до 100 символов)")
    if not phone or len(phone) > 20:
        errors.append("Телефон обязателен (до 20 символов)")

    tg_id: int | None = None
    if telegram_id and telegram_id.strip():
        try:
            tg_id = int(telegram_id)
        except ValueError:
            errors.append("Telegram ID должен быть числом")

    # Проверка уникальности telegram_id
    if tg_id is not None:
        existing = db.query(Person).filter(Person.telegram_id == tg_id).first()
        if existing:
            errors.append(f"Заказчик с Telegram ID {tg_id} уже существует")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "person/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "persons",
                "csrf_token": csrf_token,
                "person": None,
                "errors": errors,
            },
            status_code=400,
        )

    person = Person(
        first_name=first_name,
        last_name=last_name,
        second_name=second_name or None,
        phone=phone,
        telegram_id=tg_id,
    )
    db.add(person)
    db.commit()

    return RedirectResponse(url="/admin/persons", status_code=303)


@router.get("/{person_id}/edit", response_class=HTMLResponse)
async def person_edit(request: Request, person_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    person = db.query(Person).filter(Person.id == person_id).first()
    if person is None:
        raise HTTPException(status_code=404, detail="Заказчик не найден")

    csrf_token = generate_csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        "person/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "persons",
            "csrf_token": csrf_token,
            "person": person,
            "errors": None,
        },
    )


@router.post("/{person_id}/edit", response_class=HTMLResponse)
async def person_update(
    request: Request,
    person_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    second_name: str = Form(""),
    phone: str = Form(...),
    telegram_id: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    person = db.query(Person).filter(Person.id == person_id).first()
    if person is None:
        raise HTTPException(status_code=404, detail="Заказчик не найден")

    errors = []
    if not first_name or len(first_name) > 100:
        errors.append("Имя обязательно (до 100 символов)")
    if not last_name or len(last_name) > 100:
        errors.append("Фамилия обязательна (до 100 символов)")
    if not phone or len(phone) > 20:
        errors.append("Телефон обязателен (до 20 символов)")

    tg_id: int | None = None
    if telegram_id and telegram_id.strip():
        try:
            tg_id = int(telegram_id)
        except ValueError:
            errors.append("Telegram ID должен быть числом")

    if tg_id is not None:
        existing = db.query(Person).filter(
            Person.telegram_id == tg_id, Person.id != person_id
        ).first()
        if existing:
            errors.append(f"Другой заказчик с Telegram ID {tg_id} уже существует")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "person/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "persons",
                "csrf_token": csrf_token,
                "person": person,
                "errors": errors,
            },
            status_code=400,
        )

    person.first_name = first_name
    person.last_name = last_name
    person.second_name = second_name or None
    person.phone = phone
    person.telegram_id = tg_id
    db.commit()

    return RedirectResponse(url="/admin/persons", status_code=303)


@router.post("/{person_id}/delete")
async def person_delete(
    request: Request,
    person_id: int,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    person = db.query(Person).filter(Person.id == person_id).first()
    if person is None:
        raise HTTPException(status_code=404, detail="Заказчик не найден")

    # Проверяем связанные бронирования и продажи
    booking_count = db.query(func.count(Booking.id)).filter(Booking.person_id == person_id).scalar() or 0
    sale_count = db.query(func.count(Sale.id)).filter(Sale.person_id == person_id).scalar() or 0
    if booking_count or sale_count:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить заказчика: есть {booking_count} бронирований и {sale_count} продаж",
        )

    db.delete(person)
    db.commit()

    return RedirectResponse(url="/admin/persons", status_code=303)
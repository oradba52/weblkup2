"""Router продаж: /admin/sales

- Список с пагинацией, фильтром по дате
- CRUD: создание, редактирование, удаление
- При продаже товар помечается is_sold=True
- При удалении продажи — is_sold сбрасывается
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import date

from app.database import SessionLocal
from app.models.catalog import Catalog
from app.models.person import Person
from app.models.sale import Sale
from app.routers.auth import get_current_user, generate_csrf_token, verify_csrf_token

router = APIRouter(prefix="/admin/sales")

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
async def sale_list(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)

    query = db.query(Sale)
    total = query.count()
    sales = (
        query.order_by(Sale.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
        .all()
    )

    total_pages = (total + PER_PAGE - 1) // PER_PAGE

    return request.app.state.templates.TemplateResponse(
        "sale/list.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "sales",
            "csrf_token": csrf_token,
            "sales": sales,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def sale_new(
    request: Request,
    catalog_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    csrf_token = generate_csrf_token(request)

    # Товары типа "sale", которые ещё не проданы
    catalog_items = db.query(Catalog).filter(
        Catalog.type == "sale", Catalog.is_sold == False
    ).order_by(Catalog.name).all()
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()

    return request.app.state.templates.TemplateResponse(
        "sale/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "sales",
            "csrf_token": csrf_token,
            "sale": None,
            "catalog_items": catalog_items,
            "persons": persons,
            "errors": None,
            "selected_catalog_id": catalog_id,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def sale_create(
    request: Request,
    catalog_id: str = Form(...),
    person_id: str = Form(...),
    price: str = Form(...),
    sale_date: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    catalog_items = db.query(Catalog).filter(
        Catalog.type == "sale", Catalog.is_sold == False
    ).order_by(Catalog.name).all()
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
        price_val = float(price)
    except (ValueError, TypeError):
        price_val = 0
        errors.append("Цена должна быть числом")

    try:
        d_sale = date.fromisoformat(sale_date)
    except ValueError:
        d_sale = None
        errors.append("Неверный формат даты продажи")

    catalog_item = db.query(Catalog).filter(Catalog.id == cat_id).first() if cat_id else None
    person = db.query(Person).filter(Person.id == per_id).first() if per_id else None

    if catalog_item is None:
        errors.append("Товар не найден")
    elif catalog_item.type != "sale":
        errors.append("Товар не предназначен для продажи (тип — прокат)")
    elif catalog_item.is_sold:
        errors.append("Товар уже продан")

    if person is None:
        errors.append("Заказчик не найден")

    if price_val <= 0:
        errors.append("Цена должна быть больше 0")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "sale/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "sales",
                "csrf_token": csrf_token,
                "sale": None,
                "catalog_items": catalog_items,
                "persons": persons,
                "errors": errors,
                "selected_catalog_id": cat_id if cat_id else None,
            },
            status_code=400,
        )

    sale = Sale(
        catalog_id=catalog_item.id,
        person_id=person.id,
        price=price_val,
        sale_date=d_sale,
    )
    db.add(sale)

    # Помечаем товар как проданный
    catalog_item.is_sold = True
    db.commit()

    return RedirectResponse(url="/admin/sales", status_code=303)


@router.get("/{sale_id}/edit", response_class=HTMLResponse)
async def sale_edit(request: Request, sale_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="Продажа не найдена")

    csrf_token = generate_csrf_token(request)
    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()
    catalog_item = db.query(Catalog).filter(Catalog.id == sale.catalog_id).first()

    return request.app.state.templates.TemplateResponse(
        "sale/form.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "sales",
            "csrf_token": csrf_token,
            "sale": sale,
            "catalog_items": [catalog_item] if catalog_item else [],
            "persons": persons,
            "errors": None,
        },
    )


@router.post("/{sale_id}/edit", response_class=HTMLResponse)
async def sale_update(
    request: Request,
    sale_id: int,
    person_id: str = Form(...),
    price: str = Form(...),
    sale_date: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="Продажа не найдена")

    persons = db.query(Person).order_by(Person.last_name, Person.first_name).all()
    catalog_item = db.query(Catalog).filter(Catalog.id == sale.catalog_id).first()

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
        price_val = float(price)
    except (ValueError, TypeError):
        price_val = 0
        errors.append("Цена должна быть числом")

    try:
        d_sale = date.fromisoformat(sale_date)
    except ValueError:
        d_sale = None
        errors.append("Неверный формат даты продажи")

    if price_val <= 0:
        errors.append("Цена должна быть больше 0")

    if errors:
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "sale/form.html",
            {
                "request": request,
                "current_user": user,
                "active_page": "sales",
                "csrf_token": csrf_token,
                "sale": sale,
                "catalog_items": [catalog_item] if catalog_item else [],
                "persons": persons,
                "errors": errors,
            },
            status_code=400,
        )

    sale.person_id = per_id
    sale.price = price_val
    sale.sale_date = d_sale
    db.commit()

    return RedirectResponse(url="/admin/sales", status_code=303)


@router.post("/{sale_id}/delete")
async def sale_delete(
    request: Request,
    sale_id: int,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if not verify_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Ошибка CSRF")

    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="Продажа не найдена")

    # Сбрасываем флаг is_sold у товара
    catalog_item = db.query(Catalog).filter(Catalog.id == sale.catalog_id).first()
    if catalog_item:
        catalog_item.is_sold = False

    db.delete(sale)
    db.commit()

    return RedirectResponse(url="/admin/sales", status_code=303)
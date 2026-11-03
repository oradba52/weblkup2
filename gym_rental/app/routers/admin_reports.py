"""Router отчётов: /admin/reports

6 отчётов с фильтром по датам и экспортом в Excel/PDF:
1. Остатки на складе (по размерам и типам)
2. Выручка за период (продажи + прокат)
3. История бронирований за период
4. Долгосрочные/просроченные брони
5. ТОП заказчиков по выручке
6. Журнал продаж за период
"""

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import date, datetime
import io

from app.database import SessionLocal
from app.models.catalog import Catalog
from app.models.person import Person
from app.models.booking import Booking
from app.models.sale import Sale
from app.routers.auth import get_current_user

router = APIRouter(prefix="/admin/reports")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Excel helpers ──────────────────────────────────────────

def make_excel(headers: list[str], rows: list[list]) -> bytes:
    """Создаёт XLSX из заголовков и строк данных."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчёт"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, row_data in enumerate(rows, 2):
        for col_idx, val in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=val)

    # Авто-ширина
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_len:
                    max_len = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def make_pdf(title: str, headers: list[str], rows: list[list]) -> bytes:
    """Создаёт PDF-отчёт с таблицей."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), margins=[15 * mm] * 4)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=16, alignment=TA_CENTER, spaceAfter=10
    )
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 5 * mm))

    table_data = [headers]
    for row in rows:
        table_data.append([str(v) for v in row])

    col_widths = [180 / len(headers) * mm] * len(headers)
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F0F0")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def streaming_response(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_date_range(d_from: str | None, d_to: str | None) -> tuple[date | None, date | None]:
    d_from_parsed = date.fromisoformat(d_from) if d_from else None
    d_to_parsed = date.fromisoformat(d_to) if d_to else None
    return d_from_parsed, d_to_parsed


# ── Индексная страница ──────────────────────────────────────

REPORTS = [
    ("inventory", "Остатки на складе", "fas fa-warehouse", "Состояние склада по размерам и типам"),
    ("revenue", "Выручка за период", "fas fa-ruble-sign", "Доходы от продаж и проката"),
    ("bookings", "История бронирований", "fas fa-calendar-check", "Все бронирования за период"),
    ("overdue", "Просроченные брони", "fas fa-exclamation-triangle", "Не возвращённые вовремя"),
    ("top-customers", "ТОП заказчиков", "fas fa-trophy", "Самые прибыльные заказчики"),
    ("sales-journal", "Журнал продаж", "fas fa-shopping-cart", "Детализация продаж за период"),
]


@router.get("", response_class=HTMLResponse)
async def reports_index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "reports/index.html",
        {
            "request": request,
            "current_user": user,
            "active_page": "reports",
            "reports": REPORTS,
        },
    )


# ── 1. Остатки на складе ────────────────────────────────────

@router.get("/inventory", response_class=HTMLResponse)
async def report_inventory(
    request: Request,
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    # Группировка по размеру и типу
    rows_q = db.query(
        Catalog.size,
        Catalog.type,
        func.count(Catalog.id).label("total"),
        func.sum(case((Catalog.is_sold == True, 1), else_=0)).label("sold"),
        func.sum(case((Catalog.is_sold == False, 1), else_=0)).label("free"),
        func.coalesce(func.sum(Catalog.price), 0).label("total_price"),
    ).group_by(Catalog.size, Catalog.type).order_by(Catalog.size, Catalog.type).all()

    report_rows = []
    for r in rows_q:
        report_rows.append({
            "size": r.size,
            "type": "Прокат" if r.type == "rent" else "Продажа",
            "total": r.total,
            "sold": r.sold or 0,
            "free": r.free or 0,
            "total_price": float(r.total_price or 0),
        })

    if export == "excel":
        data = make_excel(
            ["Размер", "Тип", "Всего", "Продано", "Свободно", "Суммарная цена, руб."],
            [[r["size"], r["type"], r["total"], r["sold"], r["free"], r["total_price"]] for r in report_rows],
        )
        return streaming_response(data, "ostatki.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "Остатки на складе",
            ["Размер", "Тип", "Всего", "Продано", "Свободно", "Цена, руб."],
            [[r["size"], r["type"], r["total"], r["sold"], r["free"], f'{r["total_price"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "ostatki.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/inventory.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "report_name": "Остатки на складе"},
    )


# ── 2. Выручка за период ───────────────────────────────────

@router.get("/revenue", response_class=HTMLResponse)
async def report_revenue(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    d_from, d_to = parse_date_range(date_from, date_to)

    sale_query = db.query(Sale)
    if d_from:
        sale_query = sale_query.filter(Sale.sale_date >= d_from)
    if d_to:
        sale_query = sale_query.filter(Sale.sale_date <= d_to)
    sales = sale_query.order_by(Sale.sale_date.desc()).all()

    booking_query = db.query(Booking)
    if d_from:
        booking_query = booking_query.filter(Booking.data_start >= d_from)
    if d_to:
        booking_query = booking_query.filter(Booking.data_start <= d_to)
    bookings = booking_query.order_by(Booking.data_start.desc()).all()

    sale_total = sum(s.price for s in sales)
    booking_total = sum(b.total_price for b in bookings)
    grand_total = sale_total + booking_total

    report_rows = []
    for s in sales:
        report_rows.append({
            "date": s.sale_date,
            "type": "Продажа",
            "item": s.catalog.name if s.catalog else "—",
            "person": f"{s.person.last_name} {s.person.first_name}" if s.person else "—",
            "amount": s.price,
        })
    for b in bookings:
        report_rows.append({
            "date": b.data_start,
            "type": "Прокат",
            "item": b.catalog.name if b.catalog else "—",
            "person": f"{b.person.last_name} {b.person.first_name}" if b.person else "—",
            "amount": b.total_price,
        })
    report_rows.sort(key=lambda x: x["date"], reverse=True)

    if export == "excel":
        data = make_excel(
            ["Дата", "Тип", "Товар", "Заказчик", "Сумма, руб."],
            [[r["date"], r["type"], r["item"], r["person"], r["amount"]] for r in report_rows],
        )
        return streaming_response(data, "vyruchka.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "Выручка за период",
            ["Дата", "Тип", "Товар", "Заказчик", "Сумма, руб."],
            [[r["date"], r["type"], r["item"], r["person"], f'{r["amount"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "vyruchka.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/revenue.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "sale_total": sale_total, "booking_total": booking_total,
         "grand_total": grand_total, "date_from": date_from, "date_to": date_to,
         "report_name": "Выручка за период"},
    )


# ── 3. История бронирований ────────────────────────────────

@router.get("/bookings", response_class=HTMLResponse)
async def report_bookings(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    status: str | None = Query(None),
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    d_from, d_to = parse_date_range(date_from, date_to)

    query = db.query(Booking)
    if d_from:
        query = query.filter(Booking.data_start >= d_from)
    if d_to:
        query = query.filter(Booking.data_start <= d_to)
    if status and status in ("active", "returned", "cancelled"):
        query = query.filter(Booking.status == status)

    bookings = query.order_by(Booking.data_start.desc()).all()

    STATUS_MAP = {"active": "активна", "returned": "возвращена", "cancelled": "отменена"}
    report_rows = []
    for b in bookings:
        report_rows.append({
            "id": b.id,
            "item": b.catalog.name if b.catalog else "—",
            "person": f"{b.person.last_name} {b.person.first_name}" if b.person else "—",
            "start": b.data_start,
            "finish": b.data_finish,
            "fact_finish": b.fact_finish,
            "status": STATUS_MAP.get(b.status, b.status),
            "total_price": b.total_price,
        })

    if export == "excel":
        data = make_excel(
            ["№", "Товар", "Заказчик", "Начало", "Конец", "Факт. возврат", "Статус", "Сумма, руб."],
            [[r["id"], r["item"], r["person"], r["start"], r["finish"], r["fact_finish"] or "—", r["status"], r["total_price"]] for r in report_rows],
        )
        return streaming_response(data, "broni.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "История бронирований",
            ["№", "Товар", "Заказчик", "Начало", "Конец", "Факт.", "Статус", "Сумма"],
            [[r["id"], r["item"], r["person"], r["start"], r["finish"], r["fact_finish"] or "—", r["status"], f'{r["total_price"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "broni.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/bookings.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "date_from": date_from, "date_to": date_to,
         "status_filter": status, "report_name": "История бронирований"},
    )


# ── 4. Просроченные брони ──────────────────────────────────

@router.get("/overdue", response_class=HTMLResponse)
async def report_overdue(
    request: Request,
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    today = date.today()
    # Брони, где data_finish < today и status == active (нет fact_finish)
    overdue_bookings = db.query(Booking).filter(
        Booking.status == "active",
        Booking.data_finish < today,
    ).order_by(Booking.data_finish.asc()).all()

    report_rows = []
    for b in overdue_bookings:
        days_overdue = (today - b.data_finish).days
        report_rows.append({
            "id": b.id,
            "item": b.catalog.name if b.catalog else "—",
            "person": f"{b.person.last_name} {b.person.first_name}" if b.person else "—",
            "start": b.data_start,
            "finish": b.data_finish,
            "days_overdue": days_overdue,
            "total_price": b.total_price,
        })

    if export == "excel":
        data = make_excel(
            ["№", "Товар", "Заказчик", "Начало", "Конец", "Дней просрочки", "Сумма, руб."],
            [[r["id"], r["item"], r["person"], r["start"], r["finish"], r["days_overdue"], r["total_price"]] for r in report_rows],
        )
        return streaming_response(data, "prosrochennye.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "Просроченные брони",
            ["№", "Товар", "Заказчик", "Начало", "Конец", "Дней", "Сумма"],
            [[r["id"], r["item"], r["person"], r["start"], r["finish"], r["days_overdue"], f'{r["total_price"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "prosrochennye.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/overdue.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "today": today, "report_name": "Просроченные брони"},
    )


# ── 5. ТОП заказчиков ──────────────────────────────────────

@router.get("/top-customers", response_class=HTMLResponse)
async def report_top_customers(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    d_from, d_to = parse_date_range(date_from, date_to)

    # Выручка по продажам
    sale_q = db.query(
        Sale.person_id,
        func.sum(Sale.price).label("sale_revenue"),
        func.count(Sale.id).label("sale_count"),
    ).group_by(Sale.person_id)
    if d_from:
        sale_q = sale_q.filter(Sale.sale_date >= d_from)
    if d_to:
        sale_q = sale_q.filter(Sale.sale_date <= d_to)

    sale_data = {r.person_id: {"sale_revenue": float(r.sale_revenue or 0), "sale_count": r.sale_count} for r in sale_q.all()}

    # Выручка по прокату
    booking_q = db.query(
        Booking.person_id,
        func.sum(Booking.total_price).label("booking_revenue"),
        func.count(Booking.id).label("booking_count"),
    ).group_by(Booking.person_id)
    if d_from:
        booking_q = booking_q.filter(Booking.data_start >= d_from)
    if d_to:
        booking_q = booking_q.filter(Booking.data_start <= d_to)

    booking_data = {r.person_id: {"booking_revenue": float(r.booking_revenue or 0), "booking_count": r.booking_count} for r in booking_q.all()}

    # Объединяем
    all_person_ids = set(sale_data.keys()) | set(booking_data.keys())
    report_rows = []
    for pid in all_person_ids:
        person = db.query(Person).filter(Person.id == pid).first()
        if not person:
            continue
        s = sale_data.get(pid, {"sale_revenue": 0, "sale_count": 0})
        b = booking_data.get(pid, {"booking_revenue": 0, "booking_count": 0})
        total = s["sale_revenue"] + b["booking_revenue"]
        report_rows.append({
            "person_id": pid,
            "name": f"{person.last_name} {person.first_name}",
            "phone": person.phone,
            "sale_count": s["sale_count"],
            "sale_revenue": s["sale_revenue"],
            "booking_count": b["booking_count"],
            "booking_revenue": b["booking_revenue"],
            "total_revenue": total,
        })

    report_rows.sort(key=lambda x: x["total_revenue"], reverse=True)

    if export == "excel":
        data = make_excel(
            ["Заказчик", "Телефон", "Покупок", "Сумма продаж", "Броней", "Сумма проката", "Итого, руб."],
            [[r["name"], r["phone"], r["sale_count"], r["sale_revenue"], r["booking_count"], r["booking_revenue"], r["total_revenue"]] for r in report_rows],
        )
        return streaming_response(data, "top_klienty.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "ТОП заказчиков",
            ["Заказчик", "Телефон", "Покуп.", "Продажи", "Брон.", "Прокат", "Итого"],
            [[r["name"], r["phone"], r["sale_count"], f'{r["sale_revenue"]:.0f}', r["booking_count"], f'{r["booking_revenue"]:.0f}', f'{r["total_revenue"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "top_klienty.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/top_customers.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "date_from": date_from, "date_to": date_to,
         "report_name": "ТОП заказчиков"},
    )


# ── 6. Журнал продаж ───────────────────────────────────────

@router.get("/sales-journal", response_class=HTMLResponse)
async def report_sales_journal(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    export: str | None = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=303)

    d_from, d_to = parse_date_range(date_from, date_to)

    query = db.query(Sale)
    if d_from:
        query = query.filter(Sale.sale_date >= d_from)
    if d_to:
        query = query.filter(Sale.sale_date <= d_to)

    sales = query.order_by(Sale.sale_date.desc()).all()

    report_rows = []
    for s in sales:
        report_rows.append({
            "id": s.id,
            "date": s.sale_date,
            "item": s.catalog.name if s.catalog else "—",
            "size": s.catalog.size if s.catalog else "—",
            "person": f"{s.person.last_name} {s.person.first_name}" if s.person else "—",
            "phone": s.person.phone if s.person else "—",
            "price": s.price,
        })

    total = sum(r["price"] for r in report_rows)

    if export == "excel":
        data = make_excel(
            ["№", "Дата", "Товар", "Размер", "Заказчик", "Телефон", "Сумма, руб."],
            [[r["id"], r["date"], r["item"], r["size"], r["person"], r["phone"], r["price"]] for r in report_rows],
        )
        return streaming_response(data, "zhurnal_prodazh.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "Журнал продаж",
            ["№", "Дата", "Товар", "Размер", "Заказчик", "Телефон", "Сумма"],
            [[r["id"], r["date"], r["item"], r["size"], r["person"], r["phone"], f'{r["price"]:.0f}'] for r in report_rows],
        )
        return streaming_response(data, "zhurnal_prodazh.pdf", "application/pdf")

    return request.app.state.templates.TemplateResponse(
        "reports/sales_journal.html",
        {"request": request, "current_user": user, "active_page": "reports",
         "rows": report_rows, "total": total,
         "date_from": date_from, "date_to": date_to,
         "report_name": "Журнал продаж"},
    )
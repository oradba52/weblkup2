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
from sqlalchemy import func, case, and_
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
    """Создаёт XLSX потоковым writer-ом, не удерживая все ячейки в памяти."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Отчёт")
    ws.freeze_panes = "A2"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    widths = [min(max(len(str(value)) + 4, 12), 50) for value in headers]

    header_cells = []
    for index, value in enumerate(headers):
        cell = WriteOnlyCell(ws, value=value)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(cell)
    ws.append(header_cells)

    row_count = 1
    for row_data in rows:
        cells = []
        for index, value in enumerate(row_data):
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            if index >= len(widths):
                widths.append(12)
            if value is not None:
                widths[index] = min(max(widths[index], len(str(value)) + 2), 50)
            cells.append(WriteOnlyCell(ws, value=value))
        ws.append(cells)
        row_count += 1

    ws.auto_filter.ref = f"A1:{_excel_column_name(len(headers))}{row_count}"
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[_excel_column_name(index)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _excel_column_name(index: int) -> str:
    """Преобразует 1-based индекс колонки в Excel-обозначение."""
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def make_pdf(title: str, headers: list[str], rows: list[list]) -> bytes:
    """Создаёт многостраничный PDF с корректной кириллицей и переносом текста."""
    from pathlib import Path
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font_candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    )
    bold_candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    )
    regular_path = next((path for path in font_candidates if path.is_file()), None)
    bold_path = next((path for path in bold_candidates if path.is_file()), None)
    if regular_path is None or bold_path is None:
        raise RuntimeError(
            "Для PDF-отчётов необходимы шрифты DejaVu Sans с поддержкой кириллицы"
        )

    if "GymRentalDejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("GymRentalDejaVu", str(regular_path)))
    if "GymRentalDejaVu-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("GymRentalDejaVu-Bold", str(bold_path)))

    page_size = landscape(A4)
    page_width, page_height = page_size
    margin = 12 * mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=title,
        author="GymRental",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "GymRentalTitle",
        parent=styles["Title"],
        fontName="GymRentalDejaVu-Bold",
        fontSize=15,
        leading=19,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )
    header_style = ParagraphStyle(
        "GymRentalTableHeader",
        fontName="GymRentalDejaVu-Bold",
        fontSize=7,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.white,
        wordWrap="CJK",
    )
    cell_style = ParagraphStyle(
        "GymRentalTableCell",
        fontName="GymRentalDejaVu",
        fontSize=7,
        leading=9,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )

    table_data = [[Paragraph(escape(str(value)), header_style) for value in headers]]
    for row in rows:
        table_data.append([
            Paragraph(escape("" if value is None else str(value)), cell_style)
            for value in row
        ])

    available_width = page_width - 2 * margin
    column_width = available_width / max(len(headers), 1)
    table = Table(
        table_data,
        colWidths=[column_width] * len(headers),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("FONTNAME", (0, 0), (-1, 0), "GymRentalDejaVu-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "GymRentalDejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB2BD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F7")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    def draw_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("GymRentalDejaVu", 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawRightString(
            page_width - margin,
            8 * mm,
            f"Страница {document.page}",
        )
        canvas.restoreState()

    elements = [Paragraph(escape(title), title_style), Spacer(1, 2 * mm), table]
    doc.build(elements, onFirstPage=draw_page_number, onLaterPages=draw_page_number)
    return buf.getvalue()


def streaming_response(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_date_range(d_from: str | None, d_to: str | None) -> tuple[date | None, date | None]:
    try:
        d_from_parsed = date.fromisoformat(d_from) if d_from else None
        d_to_parsed = date.fromisoformat(d_to) if d_to else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD.") from exc
    if d_from_parsed and d_to_parsed and d_from_parsed > d_to_parsed:
        raise HTTPException(status_code=400, detail="Начальная дата не может быть позже конечной.")
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

    today = date.today()
    price_totals = db.query(
        Catalog.size.label("size"),
        Catalog.type.label("type"),
        func.sum(Catalog.price).label("total_price"),
    ).group_by(Catalog.size, Catalog.type).subquery()
    rows_q = db.query(
        Catalog.size,
        Catalog.type,
        func.count(func.distinct(Catalog.id)).label("total"),
        func.count(func.distinct(case((Catalog.is_sold.is_(True), Catalog.id), else_=None))).label("sold"),
        func.count(func.distinct(case((Booking.id.isnot(None), Catalog.id), else_=None))).label("booked"),
        price_totals.c.total_price,
    ).outerjoin(
        Booking,
        and_(
            Catalog.type == "rent",
            Booking.catalog_id == Catalog.id,
            Booking.status == "active",
            Booking.data_start <= today,
            Booking.data_finish >= today,
        ),
    ).join(
        price_totals,
        and_(price_totals.c.size == Catalog.size, price_totals.c.type == Catalog.type),
    ).group_by(Catalog.size, Catalog.type, price_totals.c.total_price).order_by(Catalog.size, Catalog.type).all()

    report_rows = []
    for r in rows_q:
        sold = r.sold or 0
        booked = r.booked or 0
        report_rows.append({
            "size": r.size,
            "type": "Прокат" if r.type == "rent" else "Продажа",
            "total": r.total,
            "sold": sold,
            "booked": booked,
            "free": max(r.total - sold - booked, 0),
            "total_price": float(r.total_price or 0),
        })

    if export == "excel":
        data = make_excel(
            ["Размер", "Тип", "Всего", "Продано", "Забронировано", "Свободно", "Суммарная цена, руб."],
            [[r["size"], r["type"], r["total"], r["sold"], r["booked"], r["free"], r["total_price"]] for r in report_rows],
        )
        return streaming_response(data, "ostatki.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif export == "pdf":
        data = make_pdf(
            "Остатки на складе",
            ["Размер", "Тип", "Всего", "Продано", "Бронь", "Свободно", "Цена, руб."],
            [[r["size"], r["type"], r["total"], r["sold"], r["booked"], r["free"], f'{r["total_price"]:.0f}'] for r in report_rows],
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

    booking_query = db.query(Booking).filter(Booking.status.in_(["active", "returned"]))
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
        query = query.filter(Booking.data_finish >= d_from)
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
    ).filter(Booking.status.in_(["active", "returned"])).group_by(Booking.person_id)
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
import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from io import BytesIO

from app.routers.admin_reports import make_excel, parse_date_range


def test_parse_date_range_rejects_invalid_dates():
    with pytest.raises(HTTPException) as exc:
        parse_date_range("2026-02-30", None)
    assert exc.value.status_code == 400


def test_parse_date_range_rejects_reversed_range():
    with pytest.raises(HTTPException) as exc:
        parse_date_range("2026-02-02", "2026-02-01")
    assert exc.value.status_code == 400


def test_excel_export_neutralizes_formula_like_text():
    content = make_excel(["Name"], [["=HYPERLINK('https://example.invalid')"]])
    workbook = load_workbook(BytesIO(content), data_only=False)
    cell = workbook.active["A2"]

    assert cell.data_type == "s"
    assert cell.value.startswith("'=")


def test_excel_export_handles_empty_report():
    content = make_excel(["ID", "Name"], [])
    workbook = load_workbook(BytesIO(content), read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))

    assert rows == [("ID", "Name")]


def test_pdf_export_embeds_cyrillic_font_and_escapes_cell_text():
    from app.routers.admin_reports import make_pdf

    content = make_pdf(
        "Отчёт по бронированиям",
        ["Заказчик", "Комментарий"],
        [["Иван Иванов", "<script>alert(1)</script>"]],
    )

    assert content.startswith(b"%PDF")
    assert b"/FontFile2" in content

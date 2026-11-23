"""Общие операции учёта, сериализующие изменения одного товара."""

from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.catalog import Catalog
from app.models.sale import Sale


def lock_catalog_item(db: Session, catalog_id: int) -> Catalog | None:
    """Блокирует товар до конца транзакции (включая SQLite).

    UPDATE id=id намеренно не меняет данные, но получает write lock в SQLite.
    В СУБД с row-level locking дополнительно используется SELECT FOR UPDATE.
    """
    db.execute(
        update(Catalog)
        .where(Catalog.id == catalog_id)
        .values(id=Catalog.id)
        .execution_options(synchronize_session=False)
    )
    db.flush()
    return (
        db.query(Catalog)
        .filter(Catalog.id == catalog_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def has_overlapping_booking(
    db: Session,
    catalog_id: int,
    data_start: date,
    data_finish: date,
    exclude_id: int | None = None,
) -> Booking | None:
    """Возвращает пересекающуюся активную бронь, если такая существует."""
    query = db.query(Booking).filter(
        Booking.catalog_id == catalog_id,
        Booking.status == "active",
        Booking.data_start <= data_finish,
        Booking.data_finish >= data_start,
    )
    if exclude_id is not None:
        query = query.filter(Booking.id != exclude_id)
    return query.first()


def release_catalog_after_sale_delete(
    db: Session, catalog_id: int, deleted_sale_id: int
) -> None:
    """Снимает признак продажи, только если других продаж товара не осталось."""
    another_sale = (
        db.query(Sale.id)
        .filter(
            Sale.catalog_id == catalog_id,
            Sale.id != deleted_sale_id,
        )
        .first()
    )
    if another_sale is None:
        item = lock_catalog_item(db, catalog_id)
        if item is not None:
            item.is_sold = False

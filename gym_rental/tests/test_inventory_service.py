from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Booking, Catalog, Person, Sale
from app.services.inventory_service import (
    has_overlapping_booking,
    lock_catalog_item,
    release_catalog_after_sale_delete,
)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=True)()


def make_item(db, item_type="rent", sold=False):
    item = Catalog(
        name="Test item",
        size=38,
        price=100.0,
        type=item_type,
        path="test.png",
        is_sold=sold,
    )
    db.add(item)
    db.flush()
    return item


def make_person(db):
    person = Person(first_name="Test", last_name="User", phone="000")
    db.add(person)
    db.flush()
    return person


def test_lock_catalog_item_returns_item_without_changing_it():
    db = make_db()
    try:
        item = make_item(db)
        db.commit()

        locked = lock_catalog_item(db, item.id)

        assert locked.id == item.id
        assert locked.name == "Test item"
    finally:
        db.close()


def test_overlap_uses_inclusive_dates_and_only_active_statuses():
    db = make_db()
    try:
        item = make_item(db)
        person = make_person(db)
        booking = Booking(
            catalog_id=item.id,
            person_id=person.id,
            data_start=date(2026, 1, 1),
            data_finish=date(2026, 1, 5),
            total_price=500,
            status="active",
        )
        db.add(booking)
        db.commit()

        assert has_overlapping_booking(
            db, item.id, date(2026, 1, 5), date(2026, 1, 8)
        ).id == booking.id
        assert has_overlapping_booking(
            db, item.id, date(2026, 1, 6), date(2026, 1, 8)
        ) is None
        assert has_overlapping_booking(
            db, item.id, date(2026, 1, 1), date(2026, 1, 5),
            exclude_id=booking.id,
        ) is None

        booking.status = "cancelled"
        db.commit()
        assert has_overlapping_booking(
            db, item.id, date(2026, 1, 1), date(2026, 1, 5)
        ) is None
    finally:
        db.close()


def test_deleting_one_of_multiple_sales_keeps_item_sold():
    db = make_db()
    try:
        item = make_item(db, item_type="sale", sold=True)
        person = make_person(db)
        first = Sale(catalog_id=item.id, person_id=person.id, price=90, sale_date=date(2026, 1, 1))
        second = Sale(catalog_id=item.id, person_id=person.id, price=90, sale_date=date(2026, 1, 2))
        db.add_all([first, second])
        db.commit()

        db.delete(first)
        release_catalog_after_sale_delete(db, item.id, first.id)
        db.commit()
        assert db.get(Catalog, item.id).is_sold is True

        db.delete(second)
        release_catalog_after_sale_delete(db, item.id, second.id)
        db.commit()
        assert db.get(Catalog, item.id).is_sold is False
    finally:
        db.close()

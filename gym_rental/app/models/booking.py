"""Бронирование (прокат)."""

from sqlalchemy import (
    Integer, String, Float, Date, TIMESTAMP, ForeignKey, text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime

from app.database import Base


class Booking(Base):
    __tablename__ = "booking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_start: Mapped[date] = mapped_column(Date, nullable=False)
    data_finish: Mapped[date] = mapped_column(Date, nullable=False)
    fact_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )

    catalog = relationship("Catalog", lazy="select")
    person = relationship("Person", lazy="select")

    __table_args__ = (
        Index("idx_booking_dates", "data_start", "data_finish"),
    )

"""Продажа."""

from sqlalchemy import Integer, Float, Date, TIMESTAMP, ForeignKey, text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime

from app.database import Base


class Sale(Base):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("catalog.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )

    catalog = relationship("Catalog", lazy="select")
    person = relationship("Person", lazy="select")

    __table_args__ = (
        Index("idx_sale_date", "sale_date"),
    )

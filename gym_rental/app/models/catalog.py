"""Каталог товара (купальники)."""

from sqlalchemy import Integer, String, Boolean, Float, TIMESTAMP, text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.database import Base


class Catalog(Base):
    __tablename__ = "catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="rent", index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP")
    )

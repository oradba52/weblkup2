"""Пакет моделей SQLAlchemy 2.0."""

from app.models.user import User
from app.models.login_log import LoginLog
from app.models.person import Person
from app.models.catalog import Catalog
from app.models.booking import Booking
from app.models.sale import Sale

__all__ = [
    "User",
    "LoginLog",
    "Person",
    "Catalog",
    "Booking",
    "Sale",
]

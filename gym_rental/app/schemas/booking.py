"""Pydantic-схемы для валидации форм бронирования."""

from pydantic import BaseModel, Field, field_validator
from datetime import date


class BookingCreateForm(BaseModel):
    catalog_id: int = Field(..., gt=0)
    person_id: int = Field(..., gt=0)
    data_start: date
    data_finish: date

    @field_validator("data_finish")
    @classmethod
    def validate_dates(cls, v: date, values) -> date:
        start = values.data.get("data_start")
        if start and v < start:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return v


class BookingUpdateForm(BaseModel):
    data_start: date
    data_finish: date
    status: str = Field(..., pattern="^(active|returned|cancelled)$")
    fact_finish: date | None = None
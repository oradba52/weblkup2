"""Pydantic-схемы для валидации форм продаж."""

from pydantic import BaseModel, Field
from datetime import date


class SaleCreateForm(BaseModel):
    catalog_id: int = Field(..., gt=0)
    person_id: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    sale_date: date


class SaleUpdateForm(BaseModel):
    price: float = Field(..., gt=0)
    sale_date: date
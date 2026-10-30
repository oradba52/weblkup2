"""Pydantic-схемы для валидации форм каталога."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class CatalogCreateForm(BaseModel):
    """Валидация формы создания товара."""
    name: str = Field(..., min_length=1, max_length=200)
    size: int = Field(..., ge=20, le=60)
    price: float = Field(..., gt=0)
    type: str = Field(..., pattern="^(rent|sale)$")
    is_sold: Optional[bool] = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("rent", "sale"):
            raise ValueError("Тип должен быть 'rent' или 'sale'")
        return v


class CatalogUpdateForm(BaseModel):
    """Валидация формы редактирования товара."""
    name: str = Field(..., min_length=1, max_length=200)
    size: int = Field(..., ge=20, le=60)
    price: float = Field(..., gt=0)
    type: str = Field(..., pattern="^(rent|sale)$")
    is_sold: Optional[bool] = False

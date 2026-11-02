"""Pydantic-схемы для валидации форм заказчиков."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class PersonCreateForm(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    second_name: Optional[str] = Field(None, max_length=100)
    phone: str = Field(..., min_length=3, max_length=20)
    telegram_id: Optional[int] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not cleaned.startswith("+") and not cleaned.isdigit():
            raise ValueError("Телефон должен содержать только цифры (и + в начале)")
        return v


class PersonUpdateForm(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    second_name: Optional[str] = Field(None, max_length=100)
    phone: str = Field(..., min_length=3, max_length=20)
    telegram_id: Optional[int] = None
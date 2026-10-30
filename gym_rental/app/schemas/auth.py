"""Схемы Pydantic для валидации форм."""

from pydantic import BaseModel, Field


class LoginForm(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)

"""Настройки приложения, читаемые из переменных окружения (pydantic-settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Приложение
    app_name: str = "GymRental"
    secret_key: str = "change-me-to-a-random-string"

    # База данных — SQLite по умолчанию, совместимо с PostgreSQL
    database_url: str = "sqlite:///./gym_rental.db"

    # Seed-админ
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # Загрузка файлов
    max_upload_mb: int = 5
    upload_dir: str = "app/uploads"

    # Сессия
    session_cookie_name: str = "gym_rental_session"
    session_max_age: int = 86400  # 24 часа


settings = Settings()

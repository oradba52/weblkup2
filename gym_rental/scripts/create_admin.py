"""Seed-скрипт: создаёт первого администратора.

Использование:
    python -m scripts.create_admin

Читает ADMIN_USERNAME и ADMIN_PASSWORD из .env (или переменных окружения).
Если админ с таким логином уже существует — обновляет пароль.
"""

import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password
from app.config import settings


def main():
    username = settings.admin_username
    password = settings.admin_password

    if not username or not password:
        print("ОШИБКА: ADMIN_USERNAME и ADMIN_PASSWORD должны быть заданы в .env")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            db.commit()
            print(f"Пароль администратора '{username}' обновлён.")
        else:
            admin = User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"Администратор '{username}' успешно создан.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

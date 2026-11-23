"""Создаёт первого администратора, не меняя существующие учётные записи.

Использование:
    python -m scripts.create_admin

Читает ADMIN_USERNAME и ADMIN_PASSWORD из .env или переменных окружения.
Если администратор уже существует, скрипт ничего в его учётной записи не меняет.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password
from app.config import settings


def main():
    username = settings.admin_username
    password = settings.admin_password

    if not username or not password:
        print("ОШИБКА: ADMIN_USERNAME и ADMIN_PASSWORD должны быть заданы.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.role == "admin").first()
        if existing_admin is not None:
            print(
                f"Администратор '{existing_admin.username}' уже существует. "
                "Учётная запись и пароль оставлены без изменений."
            )
            return

        existing_username = db.query(User).filter(User.username == username).first()
        if existing_username is not None:
            print(
                f"ОШИБКА: логин '{username}' уже занят неадминистратором; "
                "администратор не создан."
            )
            sys.exit(1)

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

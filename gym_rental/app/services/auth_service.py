"""Сервис авторизации: хеширование паролей, работа с сессией, логирование входов."""

import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.login_log import LoginLog


def hash_password(password: str) -> str:
    """Хеширует пароль с помощью bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_serializer() -> URLSafeTimedSerializer:
    """Создаёт сериализатор сессии с временной меткой для контроля срока жизни."""
    return URLSafeTimedSerializer(settings.secret_key, salt="gym_rental-auth")


def create_session_token(user_id: int) -> str:
    """Создаёт подписанный токен сессии для cookie."""
    return get_serializer().dumps({"user_id": user_id})


def verify_session_token(token: str) -> dict | None:
    """Проверяет подпись и срок действия токена сессии."""
    try:
        payload = get_serializer().loads(token, max_age=settings.session_max_age)
    except (BadSignature, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    user_id = payload.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return None

    return payload


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Аутентифицирует пользователя по логину/паролю."""
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def log_login_attempt(
    db: Session,
    username: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    user_id: int | None = None,
) -> None:
    """Записывает попытку входа в login_log."""
    entry = LoginLog(
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    db.add(entry)
    db.commit()

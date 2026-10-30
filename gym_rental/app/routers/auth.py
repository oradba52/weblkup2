"""Router авторизации: /login, /logout.

- /login — форма входа (GET) + обработка (POST) с CSRF-защитой
- /logout — выход, удаление cookie сессии
- Каждая попытка входа логируется в login_log
"""

from fastapi import APIRouter, Request, Response, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import secrets

from app.database import SessionLocal
from app.config import settings
from app.models.user import User
from app.services import auth_service

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Извлекает текущего пользователя из cookie сессии."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    payload = auth_service.verify_session_token(token)
    if payload is None:
        return None
    user_id = payload.get("user_id")
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Зависимость: редирект на /login если не авторизован."""
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def generate_csrf_token(request: Request) -> str:
    """Генерирует и сохраняет в сессии CSRF-токен."""
    token = secrets.token_hex(32)
    request.session["csrf_token"] = token
    return token


def verify_csrf_token(request: Request, token: str) -> bool:
    """Проверяет CSRF-токен из формы против токена в сессии."""
    session_token = request.session.get("csrf_token")
    if not session_token or not token:
        return False
    return secrets.compare_digest(session_token, token)


# --- Маршруты ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Отображает форму входа (страница AdminLTE login)."""
    csrf_token = generate_csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "csrf_token": csrf_token, "error": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    """Обрабатывает отправку формы входа."""
    # Проверка CSRF
    if not verify_csrf_token(request, csrf_token):
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "csrf_token": csrf_token, "error": "Ошибка безопасности. Попробуйте снова."},
            status_code=403,
        )

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")

    user = auth_service.authenticate_user(db, username, password)

    if user is None:
        # Логируем неудачную попытку
        auth_service.log_login_attempt(db, username, False, ip, ua, None)
        csrf_token = generate_csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "csrf_token": csrf_token, "error": "Неверный логин или пароль"},
            status_code=401,
        )

    # Логируем успешный вход
    auth_service.log_login_attempt(db, username, True, ip, ua, user.id)

    # Создаём cookie сессии
    token = auth_service.create_session_token(user.id)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout(response: Response):
    """Выход — удаляет cookie сессии."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(settings.session_cookie_name)
    return response

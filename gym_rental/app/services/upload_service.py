"""Сервис загрузки картинок: валидация, uuid-имена, структура /uploads/YYYY/MM/.

Правила:
- Разрешённые форматы: jpg, png, webp
- Максимальный размер: 5 МБ (настраивается через MAX_UPLOAD_MB)
- Имя файла заменяется на uuid + оригинальное расширение
- Файл сохраняется в app/uploads/YYYY/MM/
"""

import os
import uuid
from datetime import datetime
from fastapi import UploadFile, HTTPException

from app.config import settings

# Разрешённые MIME-типы и соответствующие расширения
ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Разрешённые расширения (двойная проверка)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


async def save_upload(file: UploadFile) -> str:
    """
    Сохраняет загруженный файл на диск.
    Возвращает относительный путь (для сохранения в БД, например: 2026/10/uuid.jpg).
    """
    # Проверка MIME-типа
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый формат файла. Разрешены: JPG, PNG, WebP",
        )

    # Проверка расширения
    original_ext = os.path.splitext(file.filename or "")[1].lower()
    if original_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимое расширение файла. Разрешены: .jpg, .png, .webp",
        )

    # Читаем содержимое и проверяем размер
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой. Максимум: {settings.max_upload_mb} МБ",
        )

    # Генерируем путь: YYYY/MM/uuid.ext
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    rel_dir = os.path.join(year, month)
    abs_dir = os.path.join(settings.upload_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    # Нормализуем расширение (jpeg → jpg)
    ext = ".jpg" if original_ext in (".jpg", ".jpeg") else original_ext
    filename = f"{uuid.uuid4().hex}{ext}"
    rel_path = os.path.join(rel_dir, filename).replace("\\", "/")
    abs_path = os.path.join(abs_dir, filename)

    with open(abs_path, "wb") as f:
        f.write(content)

    return rel_path


def delete_file(rel_path: str) -> None:
    """Удаляет файл с диска по относительному пути."""
    if not rel_path:
        return
    abs_path = os.path.join(settings.upload_dir, rel_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)

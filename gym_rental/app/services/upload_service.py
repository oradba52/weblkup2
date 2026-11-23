"""Безопасная загрузка и удаление фотографий каталога."""

import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile, HTTPException

from app.config import settings


ALLOWED_MIME = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


def _matches_image_signature(content: bytes, content_type: str) -> bool:
    """Проверяет сигнатуру файла, а не только переданный браузером MIME."""
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return (
            len(content) >= 12
            and content[0:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        )
    return False


async def save_upload(file: UploadFile) -> str:
    """
    Сохраняет файл в app/uploads/YYYY/MM/.
    Размер чтения ограничен MAX_UPLOAD_MB + 1 байт, MIME и расширение
    сверяются с сигнатурой содержимого.
    """
    content_type = (file.content_type or "").lower()
    allowed_extensions = ALLOWED_MIME.get(content_type)
    if allowed_extensions is None:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый формат файла. Разрешены: JPG, PNG, WebP",
        )

    original_ext = Path(file.filename or "").suffix.lower()
    if original_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Расширение файла не соответствует его формату",
        )

    max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой. Максимум: {settings.max_upload_mb} МБ",
        )

    if not _matches_image_signature(content, content_type):
        raise HTTPException(
            status_code=400,
            detail="Содержимое файла не соответствует формату изображения",
        )

    now = datetime.now()
    rel_dir = Path(now.strftime("%Y")) / now.strftime("%m")
    upload_root = Path(settings.upload_dir)
    abs_dir = upload_root / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    extension = ".jpg" if original_ext in (".jpg", ".jpeg") else original_ext
    filename = f"{uuid.uuid4().hex}{extension}"
    rel_path = rel_dir / filename
    abs_path = abs_dir / filename

    try:
        abs_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Не удалось сохранить файл") from exc

    return rel_path.as_posix()


def delete_file(rel_path: str) -> None:
    """Удаляет только файл, расположенный внутри каталога загрузок."""
    if not rel_path:
        return

    relative_path = Path(rel_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return

    upload_root = Path(settings.upload_dir).resolve()
    candidate = upload_root / relative_path
    resolved_candidate = candidate.resolve()

    if not resolved_candidate.is_relative_to(upload_root):
        return

    try:
        if candidate.is_file() or candidate.is_symlink():
            candidate.unlink()
    except OSError:
        # Удаление старого изображения не должно ломать основную операцию.
        return

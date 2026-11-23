import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile as StarletteUploadFile

from app import config
from app.services import upload_service


def upload(data, filename="image.png", content_type="image/png"):
    return StarletteUploadFile(
        filename=filename,
        file=BytesIO(data),
        headers={"content-type": content_type},
    )


def test_save_upload_accepts_valid_png(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "max_upload_mb", 1)
    png = b"\x89PNG\r\n\x1a\n" + b"test-image-data"

    relative_path = asyncio.run(upload_service.save_upload(upload(png)))

    saved = tmp_path / relative_path
    assert saved.is_file()
    assert saved.read_bytes() == png
    assert relative_path.endswith(".png")


def test_save_upload_rejects_mime_signature_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "upload_dir", str(tmp_path))
    file = upload(b"<html>not an image</html>")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_service.save_upload(file))

    assert exc.value.status_code == 400
    assert list(tmp_path.rglob("*")) == []


def test_save_upload_rejects_extension_mismatch():
    file = upload(b"\x89PNG\r\n\x1a\npayload", filename="image.jpg")

    with pytest.raises(HTTPException):
        asyncio.run(upload_service.save_upload(file))


def test_save_upload_enforces_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(config.settings, "max_upload_mb", 1)
    file = upload(b"\x89PNG\r\n\x1a\n" + b"x" * (1024 * 1024))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_service.save_upload(file))

    assert exc.value.status_code == 400


def test_delete_file_ignores_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "upload_dir", str(tmp_path / "uploads"))
    outside = tmp_path / "important.txt"
    outside.write_text("keep", encoding="utf-8")

    upload_service.delete_file("../important.txt")

    assert outside.read_text(encoding="utf-8") == "keep"

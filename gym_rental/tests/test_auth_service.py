from app import config
from app.services import auth_service


def test_session_token_round_trip(monkeypatch):
    monkeypatch.setattr(config.settings, "secret_key", "test-secret")
    token = auth_service.create_session_token(42)

    assert auth_service.verify_session_token(token) == {"user_id": 42}


def test_session_token_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(config.settings, "secret_key", "test-secret")

    assert auth_service.verify_session_token("not-a-valid-token") is None


def test_session_token_rejects_invalid_payload(monkeypatch):
    monkeypatch.setattr(config.settings, "secret_key", "test-secret")
    token = auth_service.get_serializer().dumps({"user_id": "42"})

    assert auth_service.verify_session_token(token) is None


def test_session_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(config.settings, "secret_key", "test-secret")
    monkeypatch.setattr(config.settings, "session_max_age", 0)
    token = auth_service.create_session_token(42)

    assert auth_service.verify_session_token(token) is None

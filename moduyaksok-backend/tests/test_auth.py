# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /auth/google, GET /me 테스트
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlmodel import select

from app.config import settings
from app.models.user import User
from app.services.auth import ALGORITHM, SESSION_COOKIE_NAME


def _mock_verify_ok(monkeypatch, google_id="google-123", email="test@example.com", name="테스터"):
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _id_token: {"google_id": google_id, "email": email, "name": name},
    )


def test_google_login_creates_user_and_sets_httponly_session_cookie(client, session, monkeypatch):
    _mock_verify_ok(monkeypatch)

    response = client.post("/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "test@example.com"
    assert body["name"] == "테스터"
    assert "picture_url" not in body
    assert "access_token" not in body
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "HttpOnly" in cookie

    user = session.exec(select(User).where(User.google_id == "google-123")).first()
    assert user is not None
    assert user.email == "test@example.com"


def test_google_login_upserts_existing_user(client, session, monkeypatch):
    _mock_verify_ok(monkeypatch, name="원래이름")
    client.post("/auth/google", json={"id_token": "fake"})

    _mock_verify_ok(monkeypatch, name="바뀐이름")
    response = client.post("/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    assert response.json()["name"] == "바뀐이름"
    users = session.exec(select(User).where(User.google_id == "google-123")).all()
    assert len(users) == 1


def test_google_login_invalid_token_returns_401(client, monkeypatch):
    def _raise(_id_token):
        raise ValueError("유효하지 않은 Google id_token입니다.")

    monkeypatch.setattr("app.routers.auth.verify_google_id_token", _raise)

    response = client.post("/auth/google", json={"id_token": "bad"})

    assert response.status_code == 401


def test_get_me_without_token_returns_401(client):
    response = client.get("/me")
    assert response.status_code == 401


def test_get_me_with_session_cookie_returns_current_user(client, monkeypatch):
    _mock_verify_ok(monkeypatch)
    login_response = client.post("/auth/google", json={"id_token": "fake"})
    assert login_response.status_code == 200
    response = client.get("/me")

    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_get_me_refreshes_session_near_expiry(client, session, monkeypatch):
    _mock_verify_ok(monkeypatch)
    client.post("/auth/google", json={"id_token": "fake"})
    user = session.exec(select(User).where(User.google_id == "google-123")).one()
    near_expiry = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(minutes=10)},
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )
    client.cookies.set(SESSION_COOKIE_NAME, near_expiry)

    response = client.get("/me")

    assert response.status_code == 200
    assert "session=" in response.headers["set-cookie"]
    refreshed = response.cookies[SESSION_COOKIE_NAME]
    payload = jwt.decode(refreshed, settings.jwt_secret_key, algorithms=[ALGORITHM])
    assert datetime.fromtimestamp(payload["exp"], tz=UTC) > datetime.now(UTC) + timedelta(
        minutes=110
    )


def test_get_me_does_not_refresh_fresh_session(client, monkeypatch):
    _mock_verify_ok(monkeypatch)
    client.post("/auth/google", json={"id_token": "fake"})

    response = client.get("/me")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_logout_clears_session_cookie(client, monkeypatch):
    _mock_verify_ok(monkeypatch)
    client.post("/auth/google", json={"id_token": "fake"})

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert 'session=""' in response.headers["set-cookie"]
    assert client.get("/me").status_code == 401


def test_cross_site_request_with_session_cookie_is_rejected(client, monkeypatch):
    _mock_verify_ok(monkeypatch)
    client.post("/auth/google", json={"id_token": "fake"})

    response = client.post("/auth/logout", headers={"Origin": "https://attacker.example"})

    assert response.status_code == 403

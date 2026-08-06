# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /auth/google, GET /me 테스트
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from sqlmodel import select

from app.models.user import User


def _mock_verify_ok(monkeypatch, google_id="google-123", email="test@example.com", name="테스터"):
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _id_token: {"google_id": google_id, "email": email, "name": name},
    )


def test_google_login_creates_user_and_returns_token(client, session, monkeypatch):
    _mock_verify_ok(monkeypatch)

    response = client.post("/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "test@example.com"
    assert body["user"]["name"] == "테스터"
    assert "picture_url" not in body["user"]

    user = session.exec(select(User).where(User.google_id == "google-123")).first()
    assert user is not None
    assert user.email == "test@example.com"


def test_google_login_upserts_existing_user(client, session, monkeypatch):
    _mock_verify_ok(monkeypatch, name="원래이름")
    client.post("/auth/google", json={"id_token": "fake"})

    _mock_verify_ok(monkeypatch, name="바뀐이름")
    response = client.post("/auth/google", json={"id_token": "fake"})

    assert response.status_code == 200
    assert response.json()["user"]["name"] == "바뀐이름"
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


def test_get_me_with_valid_token_returns_current_user(client, monkeypatch):
    _mock_verify_ok(monkeypatch)
    login_response = client.post("/auth/google", json={"id_token": "fake"})
    token = login_response.json()["access_token"]

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST/GET/DELETE /me/llm-credential, POST /me/llm-credential/test 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from sqlmodel import select

from app.models.llm_credential import LLMCredential

_VALID_ANTHROPIC_KEY = "sk-ant-abcdefghijklmnopqrstuvwx"


def _login(client, monkeypatch) -> str:
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _id_token: {
            "google_id": "google-123",
            "email": "test@example.com",
            "name": "테스터",
        },
    )
    response = client.post("/auth/google", json={"id_token": "fake"})
    return response.json()["access_token"]


def _auth_headers(client, monkeypatch) -> dict:
    return {"Authorization": f"Bearer {_login(client, monkeypatch)}"}


def test_save_credential_encrypts_key(client, session, monkeypatch):
    headers = _auth_headers(client, monkeypatch)

    response = client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["masked_key"] == "sk-ant-••••••••uvwx"

    credential = session.exec(select(LLMCredential)).first()
    assert credential is not None
    assert credential.encrypted_key != _VALID_ANTHROPIC_KEY.encode()
    assert _VALID_ANTHROPIC_KEY.encode() not in credential.encrypted_key


def test_save_credential_rejects_wrong_format(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)

    response = client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": "not-a-real-key"},
        headers=headers,
    )

    assert response.status_code == 422


def test_save_credential_upserts_single_row_per_user(client, session, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    response = client.post(
        "/me/llm-credential",
        json={"provider": "openai", "api_key": "sk-abcdefghijklmnopqrstuvwx"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    rows = session.exec(select(LLMCredential)).all()
    assert len(rows) == 1


def test_read_credential_without_registration_returns_404(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    response = client.get("/me/llm-credential", headers=headers)
    assert response.status_code == 404


def test_read_credential_returns_masked_key(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    response = client.get("/me/llm-credential", headers=headers)

    assert response.status_code == 200
    assert response.json()["masked_key"] == "sk-ant-••••••••uvwx"


def test_delete_credential_removes_row(client, session, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    response = client.delete("/me/llm-credential", headers=headers)

    assert response.status_code == 204
    assert session.exec(select(LLMCredential)).first() is None


def test_delete_credential_without_registration_returns_404(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    response = client.delete("/me/llm-credential", headers=headers)
    assert response.status_code == 404


def test_llm_credential_endpoints_require_auth(client):
    assert client.get("/me/llm-credential").status_code == 401
    assert client.delete("/me/llm-credential").status_code == 401
    assert (
        client.post(
            "/me/llm-credential", json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}
        ).status_code
        == 401
    )
    assert client.post("/me/llm-credential/test").status_code == 401


def test_test_credential_without_registration_returns_404(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    response = client.post("/me/llm-credential/test", headers=headers)
    assert response.status_code == 404


def test_test_credential_success_updates_verified_at(client, session, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )
    monkeypatch.setattr(
        "app.routers.credential.ping_provider", lambda _provider, _api_key: "안녕하세요!"
    )

    response = client.post("/me/llm-credential/test", headers=headers)

    assert response.status_code == 200
    assert response.json()["reply"] == "안녕하세요!"
    credential = session.exec(select(LLMCredential)).first()
    assert credential.verified_at is not None


def test_test_credential_provider_failure_returns_400(client, monkeypatch):
    headers = _auth_headers(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    def _raise(_provider, _api_key):
        raise RuntimeError("invalid x-api-key")

    monkeypatch.setattr("app.routers.credential.ping_provider", _raise)

    response = client.post("/me/llm-credential/test", headers=headers)

    assert response.status_code == 400

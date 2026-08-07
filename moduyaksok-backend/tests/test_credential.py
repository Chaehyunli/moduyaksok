# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST/GET/DELETE /me/llm-credential, POST /me/llm-credential/test 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 테이블 전체를 select하던 assertion을 user_id로 스코프 —
#             개발 DB에 이미 있던 실제 유저 데이터와 충돌해 테스트가 깨졌었음
# ------------------------------------------------------------------
from uuid import UUID

from sqlmodel import select

from app.models.llm_credential import LLMCredential

_VALID_ANTHROPIC_KEY = "sk-ant-abcdefghijklmnopqrstuvwx"


def _login(client, monkeypatch) -> tuple[dict, UUID]:
    """로그인 후 (인증 헤더, user_id)를 반환. DB에 이미 있는 실제 유저와 안 겹치게
    이 테스트 전용 google_id를 쓴다."""
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _id_token: {
            "google_id": "test-suite-google-id",
            "email": "test-suite@example.com",
            "name": "테스터",
        },
    )
    response = client.post("/auth/google", json={"id_token": "fake"})
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, UUID(body["user"]["id"])


def _credential_for(session, user_id: UUID) -> LLMCredential | None:
    return session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()


def test_save_credential_encrypts_key(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["masked_key"] == "sk-ant-••••••••uvwx"

    credential = _credential_for(session, user_id)
    assert credential is not None
    assert credential.encrypted_key != _VALID_ANTHROPIC_KEY.encode()
    assert _VALID_ANTHROPIC_KEY.encode() not in credential.encrypted_key


def test_save_credential_rejects_wrong_format(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": "not-a-real-key"},
        headers=headers,
    )

    assert response.status_code == 422


def test_save_credential_upserts_single_row_per_user(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
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
    rows = session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).all()
    assert len(rows) == 1


def test_read_credential_without_registration_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    response = client.get("/me/llm-credential", headers=headers)
    assert response.status_code == 404


def test_read_credential_returns_masked_key(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    response = client.get("/me/llm-credential", headers=headers)

    assert response.status_code == 200
    assert response.json()["masked_key"] == "sk-ant-••••••••uvwx"


def test_delete_credential_removes_row(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    client.post(
        "/me/llm-credential",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    response = client.delete("/me/llm-credential", headers=headers)

    assert response.status_code == 204
    assert _credential_for(session, user_id) is None


def test_delete_credential_without_registration_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
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
    headers, _ = _login(client, monkeypatch)
    response = client.post("/me/llm-credential/test", headers=headers)
    assert response.status_code == 404


def test_test_credential_success_updates_verified_at(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
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
    credential = _credential_for(session, user_id)
    assert credential.verified_at is not None


def test_test_credential_provider_failure_returns_400(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
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

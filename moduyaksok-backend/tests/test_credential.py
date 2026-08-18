# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /me/llm-credential/verify, POST/GET/DELETE /me/llm-credential,
#              POST /me/llm-credential/test 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 테이블 전체를 select하던 assertion을 user_id로 스코프
# 2026-08-12, save_credential이 저장 전 ping_provider를 호출하도록 바뀌어서,
#             이 파일 전체 테스트가 실제 provider를 호출하지 않도록 autouse로
#             기본 성공 mock을 깔아줌(프로젝트 관례: tests/*.py는 provider SDK를
#             항상 monkeypatch). 실패 케이스를 보는 테스트는 개별적으로 덮어씀.
# 2026-08-17, 클라이언트 패스프레이즈 암호화 전환 — save는 이제 암호문만
#             받고(ping_provider 호출 안 함), 저장 전 검증은 신규 /verify가
#             맡는다. 형식 검증(_KEY_PATTERNS)도 평문이 실제로 오는 /verify로
#             옮겨졌다.
# ------------------------------------------------------------------
import base64
from uuid import UUID

import pytest
from sqlmodel import select

from app.models.llm_credential import LLMCredential

_VALID_ANTHROPIC_KEY = "sk-ant-abcdefghijklmnopqrstuvwx"
_FAKE_CIPHERTEXT = base64.b64encode(b"fake-ciphertext").decode()
_FAKE_SALT = base64.b64encode(b"fake-salt-0000000").decode()
_FAKE_IV = base64.b64encode(b"fake-iv-0000").decode()
_SAVE_BODY = {
    "provider": "anthropic",
    "ciphertext": _FAKE_CIPHERTEXT,
    "salt": _FAKE_SALT,
    "iv": _FAKE_IV,
    "kdf_iterations": 600000,
    "masked_key": "sk-ant-••••••••uvwx",
}


@pytest.fixture(autouse=True)
def _mock_ping_provider_success(monkeypatch):
    monkeypatch.setattr(
        "app.routers.credential.ping_provider", lambda _provider, _api_key: "안녕하세요!"
    )


def _login(client, monkeypatch) -> tuple[dict, UUID]:
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
    return {}, UUID(body["id"])


def _credential_for(session, user_id: UUID) -> LLMCredential | None:
    return session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()


def test_save_credential_stores_ciphertext_as_sent(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)

    response = client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["masked_key"] == "sk-ant-••••••••uvwx"
    assert body["ciphertext"] == _FAKE_CIPHERTEXT

    credential = _credential_for(session, user_id)
    assert credential is not None
    assert credential.encrypted_key == base64.b64decode(_FAKE_CIPHERTEXT)
    assert credential.masked_key == "sk-ant-••••••••uvwx"


def test_save_credential_upserts_single_row_per_user(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

    other_body = {**_SAVE_BODY, "provider": "openai", "masked_key": "sk-••••••••uvwx"}
    response = client.post("/me/llm-credential", json=other_body, headers=headers)

    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    rows = session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).all()
    assert len(rows) == 1


def test_read_credential_without_registration_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    response = client.get("/me/llm-credential", headers=headers)
    assert response.status_code == 404


def test_read_credential_returns_stored_bundle(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

    response = client.get("/me/llm-credential", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["masked_key"] == "sk-ant-••••••••uvwx"
    assert body["ciphertext"] == _FAKE_CIPHERTEXT
    assert body["salt"] == _FAKE_SALT
    assert body["kdf_iterations"] == 600000


def test_delete_credential_removes_row(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

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
    assert client.post("/me/llm-credential", json=_SAVE_BODY).status_code == 401
    assert client.post("/me/llm-credential/test", json={"api_key": "x"}).status_code == 401
    assert (
        client.post(
            "/me/llm-credential/verify", json={"provider": "anthropic", "api_key": "x"}
        ).status_code
        == 401
    )


def test_verify_key_success_does_not_persist(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential/verify",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "안녕하세요!"
    assert _credential_for(session, user_id) is None


def test_verify_key_rejects_wrong_format(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential/verify",
        json={"provider": "anthropic", "api_key": "not-a-real-key"},
        headers=headers,
    )

    assert response.status_code == 422


def test_verify_key_accepts_google_key_format(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential/verify",
        json={"provider": "google", "api_key": "AIza" + "a" * 35},
        headers=headers,
    )

    assert response.status_code == 200


def test_verify_key_rejects_google_key_without_prefix(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    response = client.post(
        "/me/llm-credential/verify",
        json={"provider": "google", "api_key": "sk-" + "a" * 35},
        headers=headers,
    )

    assert response.status_code == 422


def test_verify_key_provider_failure_returns_400(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)

    def _raise(_provider, _api_key):
        raise RuntimeError("invalid x-api-key")

    monkeypatch.setattr("app.routers.credential.ping_provider", _raise)

    response = client.post(
        "/me/llm-credential/verify",
        json={"provider": "anthropic", "api_key": _VALID_ANTHROPIC_KEY},
        headers=headers,
    )

    assert response.status_code == 400


def test_test_credential_without_registration_returns_404(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    response = client.post(
        "/me/llm-credential/test", json={"api_key": _VALID_ANTHROPIC_KEY}, headers=headers
    )
    assert response.status_code == 404


def test_test_credential_success_updates_verified_at(client, session, monkeypatch):
    headers, user_id = _login(client, monkeypatch)
    client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

    response = client.post(
        "/me/llm-credential/test", json={"api_key": _VALID_ANTHROPIC_KEY}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "안녕하세요!"
    credential = _credential_for(session, user_id)
    assert credential.verified_at is not None


def test_test_credential_provider_failure_returns_400(client, monkeypatch):
    headers, _ = _login(client, monkeypatch)
    client.post("/me/llm-credential", json=_SAVE_BODY, headers=headers)

    def _raise(_provider, _api_key):
        raise RuntimeError("invalid x-api-key")

    monkeypatch.setattr("app.routers.credential.ping_provider", _raise)

    response = client.post(
        "/me/llm-credential/test", json={"api_key": _VALID_ANTHROPIC_KEY}, headers=headers
    )

    assert response.status_code == 400

# BYOK 클라이언트 패스프레이즈 암호화 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서버가 사용자의 평문 LLM API 키를 영구 저장/복호화하지 못하도록, 등록 시 사용자가 만드는 패스프레이즈로 브라우저에서 암호화하고 서버는 암호문만 보관하는 구조로 전환한다.

**Architecture:** 프런트가 Web Crypto(PBKDF2→AES-GCM)로 로컬 암호화한 뒤 암호문/salt/iv만 서버에 저장한다. 서버는 저장 시점에도, 스케줄 생성 시점에도 스스로 복호화하지 않는다 — 파이프라인이 provider를 호출해야 하는 순간(스케줄 생성/재생성/후보 교체 3곳)엔 프런트가 그때 로컬에서 복호화해 평문을 그 요청에만 실어 보내고, 서버는 처리 후 버린다. 기존에 서버 마스터키(Fernet)로 암호화돼 있던 `llm_credential` 행은 새 스킴으로 옮길 방법이 없어(패스프레이즈를 서버가 대신 만들 수 없음) 마이그레이션에서 전부 삭제하고, 영향받는 사용자는 새 화면에서 한 번 재등록한다.

**Tech Stack:** FastAPI/SQLModel/Alembic(백엔드), Vue 3/Pinia/Vitest(프런트), 브라우저 Web Crypto API(PBKDF2, AES-GCM) — 새 npm/pip 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-08-17-byok-client-side-encryption-design.md`

## Global Constraints

- KDF는 PBKDF2-SHA256, 600,000 iterations (Argon2 기각 — WASM 의존성 필요).
- salt(16byte)/iv(12byte)는 매 암호화마다 새로 생성, 비밀 아님(DB/응답에 평문 저장 가능).
- 패스프레이즈 원문은 유도 직후 버리고, 유도된 `CryptoKey`만 Pinia store에 메모리로만 캐시(persist 안 함, 새로고침 시 소실).
- 기존 `llm_credential` 행은 마이그레이션에서 전부 삭제 — 신구 스킴 병행 지원 없음.
- `user` 테이블은 이번 변경과 무관, 그대로 유지.
- `tests/*.py`는 provider SDK를 항상 monkeypatch(백엔드 CLAUDE.md 관례) — 이 규칙은 이번 작업에서도 그대로 따른다.

---

## Task 1: 백엔드 — `llm_credential` 스키마 전환 + `credential.py` 라우터 재작성

**Files:**
- Modify: `moduyaksok-backend/app/models/llm_credential.py`
- Create: `moduyaksok-backend/alembic/versions/a1c9f2b8e4d0_llm_credential_client_side_encryption.py`
- Modify: `moduyaksok-backend/app/routers/credential.py`
- Delete: `moduyaksok-backend/app/services/credential.py`
- Modify: `moduyaksok-backend/tests/test_credential.py` (전체 재작성)
- Modify: `moduyaksok-backend/.env.example` (`CREDENTIAL_ENCRYPTION_KEY` 줄 삭제)
- Modify: `moduyaksok-backend/app/config.py` (`credential_encryption_key` 필드 삭제)

**Interfaces:**
- Produces: `LLMCredential` 모델의 새 필드(`salt: bytes`, `iv: bytes`, `kdf_iterations: int`, `masked_key: str`) — Task 2가 `credential.provider`만 그대로 쓰므로 영향 없음.
- Produces: `POST /me/llm-credential/verify` (신규), `POST /me/llm-credential`·`GET /me/llm-credential`·`POST /me/llm-credential/test`·`DELETE /me/llm-credential`(계약 변경) — 프런트 Task 4/5가 소비.

- [ ] **Step 1: `LLMCredential` 모델에 새 컬럼 추가**

`moduyaksok-backend/app/models/llm_credential.py` 전체를 다음으로 교체:

```python
# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 사용자별 LLM API 키(BYOK) 저장 테이블 정의
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, provider 기본값 제거, 등록 시 Claude/GPT 중 선택 필수로 변경
# 2026-08-06, __tablename__ 명시 (SQLModel 기본 테이블명이 ERD의 snake_case와 불일치해서 수정)
# 2026-08-17, 서버 Fernet 마스터키 암호화 → 클라이언트 패스프레이즈 유도 AES-GCM
#             암호화로 전환(docs/superpowers/specs/2026-08-17-byok-client-side-
#             encryption-design.md). encrypted_key는 이제 클라이언트가 만든
#             암호문을 그대로 담고, 복호화에 필요한 salt/iv/kdf_iterations와
#             표시용 masked_key가 추가됐다. 서버는 이 컬럼들을 해석하지 않고
#             그대로 저장/반환만 한다.
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class LLMCredential(SQLModel, table=True):
    __tablename__ = "llm_credential"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id", unique=True)
    provider: str  # "anthropic" | "openai" | "upstage" | "google" — 라우터의 Literal이 값 제한
    encrypted_key: bytes  # 클라이언트가 패스프레이즈 유도 키로 AES-GCM 암호화한 값
    salt: bytes  # PBKDF2 salt — 비밀 아님
    iv: bytes  # AES-GCM iv — 비밀 아님
    kdf_iterations: int
    masked_key: str  # 클라이언트가 계산해 같이 보낸 마스킹 값 (예: "sk-ant-••••••••uvwx")
    verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Alembic 마이그레이션 작성**

`moduyaksok-backend/alembic/versions/a1c9f2b8e4d0_llm_credential_client_side_encryption.py` 신규 생성:

```python
"""llm_credential client-side encryption columns

Revision ID: a1c9f2b8e4d0
Revises: f4f8459f626b
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9f2b8e4d0'
down_revision: Union[str, Sequence[str], None] = 'f4f8459f626b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    기존 encrypted_key는 서버 마스터키(Fernet)로 암호화된 값이라 새 스킴(클라이언트
    패스프레이즈 유도 AES-GCM)으로 옮길 방법이 없다 — 서버가 대신 패스프레이즈를
    만들어 줄 수 없기 때문(docs/superpowers/specs/2026-08-17-byok-client-side-
    encryption-design.md §6). 기존 행은 폐기하고, 사용자는 새 화면에서 한 번
    재등록해야 한다.
    """
    op.execute("DELETE FROM llm_credential")
    op.add_column('llm_credential', sa.Column('salt', sa.LargeBinary(), nullable=False))
    op.add_column('llm_credential', sa.Column('iv', sa.LargeBinary(), nullable=False))
    op.add_column('llm_credential', sa.Column('kdf_iterations', sa.Integer(), nullable=False))
    op.add_column('llm_credential', sa.Column('masked_key', sa.String(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('llm_credential', 'masked_key')
    op.drop_column('llm_credential', 'kdf_iterations')
    op.drop_column('llm_credential', 'iv')
    op.drop_column('llm_credential', 'salt')
```

- [ ] **Step 3: 마이그레이션 적용**

Run: `cd moduyaksok-backend && alembic upgrade head`
Expected: 에러 없이 완료. (dev DB가 안 떠 있으면 먼저 `cd moduyaksok-db && docker compose up -d`)

- [ ] **Step 4: `credential.py` 라우터 재작성 — 실패하는 테스트부터**

`moduyaksok-backend/tests/test_credential.py` 전체를 다음으로 교체 (기존 파일 완전 대체):

```python
# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /me/llm-credential/verify, POST/GET/DELETE /me/llm-credential,
#              POST /me/llm-credential/test 테스트
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 테이블 전체를 select하던 assertion을 user_id로 스코프
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
```

- [ ] **Step 5: 테스트 실행해서 실패 확인**

Run: `cd moduyaksok-backend && pytest tests/test_credential.py -v`
Expected: FAIL — `/me/llm-credential/verify` 404(라우트 없음), 기존 `save_credential`이 `api_key`를 요구해 `_SAVE_BODY`(ciphertext 필드들)로는 422 등.

- [ ] **Step 6: `credential.py` 라우터 구현**

`moduyaksok-backend/app/routers/credential.py` 전체를 다음으로 교체:

```python
# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /me/llm-credential/verify — 저장 전 평문 키를 provider에 테스트만(저장 안 함)
#              POST/GET/DELETE /me/llm-credential — 클라이언트가 이미 암호화한 값 저장/조회/삭제
#              POST /me/llm-credential/test — 프런트가 로컬 복호화해 보낸 평문으로 재확인
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, /me/llm-credential/test 추가
# 2026-08-12, 등록 시 저장 전 ping_provider로 1회 테스트
# 2026-08-17, 클라이언트 패스프레이즈 암호화로 전환(docs/superpowers/specs/
#             2026-08-17-byok-client-side-encryption-design.md). 서버는 평문
#             API 키를 저장 시점에 다시는 보지 않는다 — save는 클라이언트가
#             이미 암호화한 ciphertext/salt/iv만 받아 그대로 저장하고,
#             "저장 전 유효성 확인"은 신규 /verify(평문을 받되 저장 안 함)로
#             옮겼다. test도 서버가 스스로 복호화하지 못하므로 body로 평문을
#             받는다. 이 변경으로 encrypt_key/decrypt_key/mask_key(서버 Fernet
#             레이어, services/credential.py)는 전부 삭제.
# ------------------------------------------------------------------
import base64
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.llm_credential import LLMCredential
from app.models.user import User
from app.services.auth import get_current_user
from app.services.llm_ping import ping_provider

router = APIRouter()

Provider = Literal["anthropic", "openai", "upstage", "google"]

# 발급 기관이 공개한 키 접두사 기준. /verify에 평문이 들어올 때만 검증 가능 —
# save는 암호문만 받으므로 여기서 형식을 알 수 없다.
_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$"),
    "openai": re.compile(r"^sk-[A-Za-z0-9_-]{20,}$"),
    "upstage": re.compile(r"^up_[A-Za-z0-9]{20,}$"),
    "google": re.compile(r"^AIza[A-Za-z0-9_-]{30,}$"),
}


def _validate_key_format(provider: str, api_key: str) -> None:
    pattern = _KEY_PATTERNS.get(provider)
    if pattern and not pattern.match(api_key):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"{provider} API 키 형식이 아닙니다."
        )


class VerifyKeyRequest(BaseModel):
    provider: Provider
    api_key: str


class VerifyKeyOut(BaseModel):
    reply: str


class CredentialSaveRequest(BaseModel):
    provider: Provider
    ciphertext: str  # base64
    salt: str  # base64
    iv: str  # base64
    kdf_iterations: int
    masked_key: str


class CredentialOut(BaseModel):
    provider: str
    masked_key: str
    ciphertext: str
    salt: str
    iv: str
    kdf_iterations: int


class TestCredentialRequest(BaseModel):
    api_key: str


class CredentialTestOut(BaseModel):
    reply: str


def _b64d(value: str) -> bytes:
    return base64.b64decode(value)


def _b64e(value: bytes) -> str:
    return base64.b64encode(value).decode()


def _get_credential(session: Session, user_id) -> LLMCredential | None:
    return session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()


@router.post("/me/llm-credential/verify", response_model=VerifyKeyOut)
def verify_key(
    body: VerifyKeyRequest,
    current_user: User = Depends(get_current_user),
) -> VerifyKeyOut:
    _validate_key_format(body.provider, body.api_key)
    try:
        reply = ping_provider(body.provider, body.api_key)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"API 키 테스트에 실패했어요: {exc}"
        ) from exc
    return VerifyKeyOut(reply=reply)


@router.post("/me/llm-credential", response_model=CredentialOut)
def save_credential(
    body: CredentialSaveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialOut:
    existing = _get_credential(session, current_user.id)
    if existing is None:
        existing = LLMCredential(user_id=current_user.id, provider=body.provider)
    existing.provider = body.provider
    existing.encrypted_key = _b64d(body.ciphertext)
    existing.salt = _b64d(body.salt)
    existing.iv = _b64d(body.iv)
    existing.kdf_iterations = body.kdf_iterations
    existing.masked_key = body.masked_key
    existing.verified_at = None
    session.add(existing)
    session.commit()
    return CredentialOut(
        provider=body.provider,
        masked_key=body.masked_key,
        ciphertext=body.ciphertext,
        salt=body.salt,
        iv=body.iv,
        kdf_iterations=body.kdf_iterations,
    )


@router.get("/me/llm-credential", response_model=CredentialOut)
def read_credential(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialOut:
    credential = _get_credential(session, current_user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    return CredentialOut(
        provider=credential.provider,
        masked_key=credential.masked_key,
        ciphertext=_b64e(credential.encrypted_key),
        salt=_b64e(credential.salt),
        iv=_b64e(credential.iv),
        kdf_iterations=credential.kdf_iterations,
    )


@router.post("/me/llm-credential/test", response_model=CredentialTestOut)
def test_credential(
    body: TestCredentialRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialTestOut:
    credential = _get_credential(session, current_user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    try:
        reply = ping_provider(credential.provider, body.api_key)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"API 키 테스트에 실패했어요: {exc}"
        ) from exc
    credential.verified_at = datetime.utcnow()
    session.add(credential)
    session.commit()
    return CredentialTestOut(reply=reply)


@router.delete("/me/llm-credential", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    credential = _get_credential(session, current_user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    session.delete(credential)
    session.commit()
```

- [ ] **Step 7: `app/services/credential.py` 삭제**

Run: `cd moduyaksok-backend && rm app/services/credential.py`

- [ ] **Step 8: `config.py`에서 `credential_encryption_key` 필드 삭제**

`moduyaksok-backend/app/config.py`에서 다음 줄을 제거:

```python
    credential_encryption_key: str = ""

```
(`google_client_id`/`frontend_url` 다음, `# 개발 편의용 폴백 키` 주석 앞의 빈 줄 포함 삭제)

- [ ] **Step 9: `.env.example`에서 `CREDENTIAL_ENCRYPTION_KEY` 삭제**

`moduyaksok-backend/.env.example`의 `CREDENTIAL_ENCRYPTION_KEY=` 줄 삭제.

- [ ] **Step 10: 테스트 실행해서 통과 확인**

Run: `cd moduyaksok-backend && pytest tests/test_credential.py -v`
Expected: PASS (전체)

- [ ] **Step 11: 커밋**

```bash
git add moduyaksok-backend/app/models/llm_credential.py moduyaksok-backend/alembic/versions/a1c9f2b8e4d0_llm_credential_client_side_encryption.py moduyaksok-backend/app/routers/credential.py moduyaksok-backend/tests/test_credential.py moduyaksok-backend/.env.example moduyaksok-backend/app/config.py
git rm moduyaksok-backend/app/services/credential.py
git commit -m "feat: BYOK 키를 클라이언트 패스프레이즈 암호화로 전환 (백엔드)"
```

---

## Task 2: 백엔드 — 스케줄 생성 엔드포인트에 평문 `api_key` 스레딩

**Files:**
- Modify: `moduyaksok-backend/app/routers/schedule.py`
- Modify: `moduyaksok-backend/tests/test_schedule.py`
- Modify: `moduyaksok-backend/tests/test_share.py`

**Interfaces:**
- Consumes: Task 1의 `LLMCredential`(변경 없는 `.provider` 필드만 사용).
- Produces: `ScheduleCreateRequest.api_key`, `RegenerateScheduleRequest.api_key`, `CandidateReplacementPreviewRequest.api_key` — Task 6(프런트)가 이 필드들에 평문 키를 채워 보낸다.

- [ ] **Step 1: `decrypt_key` import 제거, 요청 모델에 `api_key` 필드 추가**

`moduyaksok-backend/app/routers/schedule.py`에서:

```python
from app.services.credential import decrypt_key
```
줄 삭제.

`ScheduleCreateRequest`(현재 정의):
```python
class ScheduleCreateRequest(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
    liked_text: str = Field(default="", max_length=50)
    disliked_text: str = Field(default="", max_length=50)
    budget_per_person: int
```
→
```python
class ScheduleCreateRequest(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
    liked_text: str = Field(default="", max_length=50)
    disliked_text: str = Field(default="", max_length=50)
    budget_per_person: int
    api_key: str  # 클라이언트가 로컬에서 복호화해 실어 보낸 평문. 서버는 저장하지 않는다.
```

`RoutesRequest` 클래스 바로 뒤에 신규 모델 추가:
```python
class RoutesRequest(BaseModel):
    candidate_id: str


class RegenerateScheduleRequest(BaseModel):
    api_key: str  # 클라이언트가 로컬에서 복호화해 실어 보낸 평문. 서버는 저장하지 않는다.
```

`CandidatePreviewRequest` 바로 뒤에 신규 서브클래스 추가:
```python
class CandidatePreviewRequest(BaseModel):
    excluded_place_ids: list[str]


class CandidateReplacementPreviewRequest(CandidatePreviewRequest):
    """장소 교체 미리보기는 파이프라인을 실제로 호출하므로 평문 API 키가 필요하다
    (removal/preview는 로컬 재계산만 하므로 CandidatePreviewRequest 그대로 사용)."""

    api_key: str
```

- [ ] **Step 2: `_generate_candidate_replacement`가 `api_key`를 파라미터로 받도록 변경**

```python
async def _generate_candidate_replacement(
    session: Session,
    schedule_session: ScheduleSession,
    current_user: User,
    candidate_id: str,
    excluded_place_ids: set[str],
    replacement_count: int = 1,
) -> Candidate:
```
→
```python
async def _generate_candidate_replacement(
    session: Session,
    schedule_session: ScheduleSession,
    current_user: User,
    candidate_id: str,
    excluded_place_ids: set[str],
    api_key: str,
    replacement_count: int = 1,
) -> Candidate:
```

함수 본문의:
```python
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)
    import asyncio
```
→
```python
    credential = _get_user_credential(session, current_user.id)
    import asyncio
```

- [ ] **Step 3: `preview_candidate_replacement`가 새 요청 모델을 쓰고 `api_key`를 전달**

```python
async def preview_candidate_replacement(
    session_id: UUID,
    candidate_id: str,
    body: CandidatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
```
의 `body: CandidatePreviewRequest,`를 `body: CandidateReplacementPreviewRequest,`로 변경.

같은 함수 안:
```python
    updated = await _generate_candidate_replacement(
        session,
        schedule_session,
        current_user,
        candidate_id,
        combined_exclusions,
        len(requested_exclusions) or 1,
    )
```
→
```python
    updated = await _generate_candidate_replacement(
        session,
        schedule_session,
        current_user,
        candidate_id,
        combined_exclusions,
        body.api_key,
        len(requested_exclusions) or 1,
    )
```

- [ ] **Step 4: `create_schedule`이 body의 `api_key`를 쓰도록 변경**

```python
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)

    session_id = uuid4()
```
→
```python
    credential = _get_user_credential(session, current_user.id)
    api_key = body.api_key

    session_id = uuid4()
```

- [ ] **Step 5: `regenerate_schedule`이 body를 받도록 변경**

```python
@router.post("/schedules/{session_id}/regenerate", response_model=ScheduleResponse)
async def regenerate_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
```
→
```python
@router.post("/schedules/{session_id}/regenerate", response_model=ScheduleResponse)
async def regenerate_schedule(
    session_id: UUID,
    body: RegenerateScheduleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
```

같은 함수 안:
```python
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)
    if schedule_session.normalized_conditions:
```
→
```python
    credential = _get_user_credential(session, current_user.id)
    api_key = body.api_key
    if schedule_session.normalized_conditions:
```

- [ ] **Step 6: `test_schedule.py` 픽스처를 새 스키마에 맞게 수정**

`_register_credential` 및 관련 import 교체:
```python
from app.services.credential import encrypt_key
```
줄 삭제.

```python
def _register_credential(session, user_id: UUID) -> None:
    session.add(
        LLMCredential(
            user_id=user_id, provider="anthropic", encrypted_key=encrypt_key("sk-ant-fake-key")
        )
    )
    session.commit()
```
→
```python
def _register_credential(session, user_id: UUID) -> None:
    session.add(
        LLMCredential(
            user_id=user_id,
            provider="anthropic",
            encrypted_key=b"fake-ciphertext",
            salt=b"fake-salt-0000000",
            iv=b"fake-iv-0000",
            kdf_iterations=600_000,
            masked_key="sk-ant-••••••••uvwx",
        )
    )
    session.commit()
```

`_CREATE_BODY`에 `api_key` 추가:
```python
_CREATE_BODY = {
    "purpose": "date",
    "headcount": 2,
    "time_range": _TIME_RANGE,
    "region": "서울 강남",
    "liked_text": "",
    "disliked_text": "",
    "budget_per_person": 50000,
}
```
→
```python
_CREATE_BODY = {
    "purpose": "date",
    "headcount": 2,
    "time_range": _TIME_RANGE,
    "region": "서울 강남",
    "liked_text": "",
    "disliked_text": "",
    "budget_per_person": 50000,
    "api_key": "sk-ant-fake-key",
}
```

- [ ] **Step 7: `regenerate` 호출 5곳에 `json` 추가**

파일 전체에서 다음 부분 문자열을 찾아(5곳: 약 709, 1360, 1369, 1890, 1917번 줄) `replace_all`로 교체:

old:
```python
client.post(f"/schedules/{session_id}/regenerate", headers=headers)
```
new:
```python
client.post(
            f"/schedules/{session_id}/regenerate",
            json={"api_key": "sk-ant-fake-key"},
            headers=headers,
        )
```

(각 호출부의 기존 들여쓰기/변수 할당(`response =`, `first =`, `second =`)은 그대로 유지하고 `client.post(...)` 부분만 위와 같이 여러 줄로 바꾼다.)

- [ ] **Step 8: `.../candidates/A/preview` 호출 6곳에 `api_key` 추가**

각 호출의 `json={"excluded_place_ids": [...]}`를 `json={"excluded_place_ids": [...], "api_key": "sk-ant-fake-key"}`로 바꾼다. 6곳:

1. (약 782번 줄, `test_replacement_preview_...` — `preview_response` 변수) `json={"excluded_place_ids": [excluded_place_id]}` → `json={"excluded_place_ids": [excluded_place_id], "api_key": "sk-ant-fake-key"}`
2. (약 1005번 줄) `json={"excluded_place_ids": [first_removed_id, "removed-afternoon"]}` → `json={"excluded_place_ids": [first_removed_id, "removed-afternoon"], "api_key": "sk-ant-fake-key"}`
3. (약 1063번 줄, `test_replacement_preview_adds_one_place_without_exclusions`) `json={"excluded_place_ids": []}` → `json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"}`
4. (약 1170번 줄, 뒤에 `"custom-1" in captured["place_ids"]` 검증이 있는 테스트) `json={"excluded_place_ids": []}` → `json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"}`
5. (약 1199번 줄, `test_replacement_preview_rejects_add_when_already_at_max_places`) `json={"excluded_place_ids": []}` → `json={"excluded_place_ids": [], "api_key": "sk-ant-fake-key"}`
6. (약 1261번 줄, `test_candidate_preview_rejects_required_place`) `json={"excluded_place_ids": [place_id]}` → `json={"excluded_place_ids": [place_id], "api_key": "sk-ant-fake-key"}`

각각 파일에서 해당 테스트 함수명 또는 바로 앞뒤 고유한 줄(위에 적은 단서)로 위치를 확인한 뒤 개별적으로 교체 — `excluded_place_ids: []`가 여러 곳에 나오므로 `replace_all`을 쓰지 말고 하나씩 확인하며 바꿀 것.

- [ ] **Step 9: `test_replacement_preview_adds_one_place_without_exclusions`의 `fake_replacement` 시그니처 수정**

```python
    async def fake_replacement(_session, _schedule_session, _current_user, _candidate_id, excluded, count):
        captured["excluded"] = excluded
        captured["count"] = count
        return replacement
```
→
```python
    async def fake_replacement(
        _session, _schedule_session, _current_user, _candidate_id, excluded, _api_key, count
    ):
        captured["excluded"] = excluded
        captured["count"] = count
        return replacement
```

(다른 `fake_replacement`들은 `*_args, **_kwargs`를 쓰므로 수정 불필요.)

- [ ] **Step 10: `test_share.py` 픽스처 수정**

```python
from app.services.credential import encrypt_key
```
줄 삭제.

```python
def _register_credential(session, user_id: UUID) -> None:
    session.add(
        LLMCredential(
            user_id=user_id, provider="anthropic", encrypted_key=encrypt_key("sk-ant-fake-key")
        )
    )
    session.commit()
```
→ Task 1과 동일한 새 필드 채운 형태로 교체:
```python
def _register_credential(session, user_id: UUID) -> None:
    session.add(
        LLMCredential(
            user_id=user_id,
            provider="anthropic",
            encrypted_key=b"fake-ciphertext",
            salt=b"fake-salt-0000000",
            iv=b"fake-iv-0000",
            kdf_iterations=600_000,
            masked_key="sk-ant-••••••••uvwx",
        )
    )
    session.commit()
```

파일 안에 동일하게 3번 반복되는 다음 블록(약 98, 218, 275번 줄)을 `replace_all`로 교체:

old:
```python
        "budget_per_person": 50000,
    }
```
new:
```python
        "budget_per_person": 50000,
        "api_key": "sk-ant-fake-key",
    }
```

- [ ] **Step 11: 백엔드 전체 테스트 실행**

Run: `cd moduyaksok-backend && pytest -q`
Expected: PASS (전체)

- [ ] **Step 12: 커밋**

```bash
git add moduyaksok-backend/app/routers/schedule.py moduyaksok-backend/tests/test_schedule.py moduyaksok-backend/tests/test_share.py
git commit -m "feat: 스케줄 생성 엔드포인트가 클라이언트가 보낸 평문 api_key를 쓰도록 변경"
```

---

## Task 3: 프런트 — `credentialCrypto.ts` (PBKDF2 + AES-GCM)

**Files:**
- Create: `moduyaksok-frontend/src/lib/credentialCrypto.ts`
- Create: `moduyaksok-frontend/src/lib/credentialCrypto.spec.ts`

**Interfaces:**
- Produces: `EncryptedBundle` 타입, `encryptApiKey(passphrase, apiKey)`, `deriveKeyFromBundle(passphrase, bundle)`, `decryptApiKey(derivedKey, bundle)`, `maskKey(rawKey)` — Task 4(`credentialSession` store)와 Task 5(`ApiKeyEditView.vue`)가 소비.

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-frontend/src/lib/credentialCrypto.spec.ts` 신규 생성:

```ts
import { describe, expect, it } from 'vitest'
import { decryptApiKey, deriveKeyFromBundle, encryptApiKey, maskKey } from './credentialCrypto'

describe('credentialCrypto', () => {
  it('암호화한 값을 같은 패스프레이즈로 그대로 복호화한다', async () => {
    const bundle = await encryptApiKey('correct horse battery staple', 'sk-ant-abc123')
    const key = await deriveKeyFromBundle('correct horse battery staple', bundle)

    const decrypted = await decryptApiKey(key, bundle)

    expect(decrypted).toBe('sk-ant-abc123')
  })

  it('틀린 패스프레이즈로 복호화하면 예외를 던진다', async () => {
    const bundle = await encryptApiKey('correct horse battery staple', 'sk-ant-abc123')
    const wrongKey = await deriveKeyFromBundle('wrong passphrase', bundle)

    await expect(decryptApiKey(wrongKey, bundle)).rejects.toThrow()
  })

  it('앞 7자/뒤 4자만 남기고 마스킹한다', () => {
    expect(maskKey('sk-ant-abcdefghijklmnopqrstuvwx')).toBe('sk-ant-••••••••uvwx')
  })
})
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd moduyaksok-frontend && npx vitest run src/lib/credentialCrypto.spec.ts`
Expected: FAIL — `./credentialCrypto` 모듈이 없음

- [ ] **Step 3: `credentialCrypto.ts` 구현**

`moduyaksok-frontend/src/lib/credentialCrypto.ts` 신규 생성:

```ts
// PBKDF2(패스프레이즈 → 키 유도) + AES-GCM(암호화)로 BYOK API 키를 브라우저에서만
// 암호화한다. 서버는 ciphertext/salt/iv/kdf_iterations만 보고 평문은 절대 못 본다
// (docs/superpowers/specs/2026-08-17-byok-client-side-encryption-design.md).
const PBKDF2_ITERATIONS = 600_000

export interface EncryptedBundle {
  ciphertext: string // base64
  salt: string // base64
  iv: string // base64
  kdfIterations: number
}

function toBase64(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
}

function fromBase64(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (c) => c.charCodeAt(0))
}

async function deriveKey(
  passphrase: string,
  salt: Uint8Array,
  iterations: number,
): Promise<CryptoKey> {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export function deriveKeyFromBundle(
  passphrase: string,
  bundle: Pick<EncryptedBundle, 'salt' | 'kdfIterations'>,
): Promise<CryptoKey> {
  return deriveKey(passphrase, fromBase64(bundle.salt), bundle.kdfIterations)
}

export async function encryptApiKey(passphrase: string, apiKey: string): Promise<EncryptedBundle> {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt, PBKDF2_ITERATIONS)
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(apiKey),
  )
  return {
    ciphertext: toBase64(encrypted),
    salt: toBase64(salt.buffer as ArrayBuffer),
    iv: toBase64(iv.buffer as ArrayBuffer),
    kdfIterations: PBKDF2_ITERATIONS,
  }
}

export async function decryptApiKey(
  derivedKey: CryptoKey,
  bundle: Pick<EncryptedBundle, 'ciphertext' | 'iv'>,
): Promise<string> {
  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: fromBase64(bundle.iv) },
    derivedKey,
    fromBase64(bundle.ciphertext),
  )
  return new TextDecoder().decode(decrypted)
}

export function maskKey(rawKey: string): string {
  return rawKey.slice(0, 7) + '••••••••' + rawKey.slice(-4)
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd moduyaksok-frontend && npx vitest run src/lib/credentialCrypto.spec.ts`
Expected: PASS (3개 전부)

- [ ] **Step 5: 커밋**

```bash
git add moduyaksok-frontend/src/lib/credentialCrypto.ts moduyaksok-frontend/src/lib/credentialCrypto.spec.ts
git commit -m "feat: BYOK 키 클라이언트 암호화 유틸(PBKDF2+AES-GCM) 추가"
```

---

## Task 4: 프런트 — `credentialSession` store + `PassphraseModal.vue`

**Files:**
- Create: `moduyaksok-frontend/src/stores/credentialSession.ts`
- Create: `moduyaksok-frontend/src/stores/credentialSession.spec.ts`
- Create: `moduyaksok-frontend/src/components/doodle/PassphraseModal.vue`
- Modify: `moduyaksok-frontend/src/App.vue`

**Interfaces:**
- Consumes: Task 3의 `encryptApiKey`/`deriveKeyFromBundle`/`decryptApiKey`/`EncryptedBundle`.
- Produces: `useCredentialSessionStore().ensureDecryptedApiKey(): Promise<string>`, `.setBundle(bundle)`, `.clear()` — Task 5(`ApiKeyEditView.vue`)와 Task 6(`stores/schedule.ts`)가 소비.

- [ ] **Step 1: 실패하는 테스트 작성**

`moduyaksok-frontend/src/stores/credentialSession.spec.ts` 신규 생성:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '../lib/api'
import { deriveKeyFromBundle, encryptApiKey } from '../lib/credentialCrypto'
import { useCredentialSessionStore } from './credentialSession'

vi.mock('../lib/api', () => ({
  api: { get: vi.fn() },
}))

const apiGet = vi.mocked(api.get)

describe('credentialSession 스토어', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockReset()
  })

  it('캐시된 유도키가 있으면 API를 다시 부르지 않고 즉시 복호화한다', async () => {
    const bundle = await encryptApiKey('패스프레이즈', 'sk-ant-cached')
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }
    store.derivedKey = await deriveKeyFromBundle('패스프레이즈', bundle)

    const key = await store.ensureDecryptedApiKey()

    expect(key).toBe('sk-ant-cached')
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('패스프레이즈가 틀리면 에러를 남기고 유도키를 캐시하지 않는다', async () => {
    const bundle = await encryptApiKey('올바른패스프레이즈', 'sk-ant-x')
    const store = useCredentialSessionStore()
    store.bundle = { provider: 'anthropic', ...bundle }

    await store.submitPassphrase('틀린패스프레이즈')

    expect(store.passphraseError).toBe('패스프레이즈가 틀렸어요')
    expect(store.derivedKey).toBeNull()
  })

  it('패스프레이즈가 맞으면 대기 중이던 요청을 평문으로 해결한다', async () => {
    const bundle = await encryptApiKey('내패스프레이즈', 'sk-ant-y')
    apiGet.mockResolvedValueOnce({
      data: {
        provider: 'anthropic',
        ciphertext: bundle.ciphertext,
        salt: bundle.salt,
        iv: bundle.iv,
        kdf_iterations: bundle.kdfIterations,
      },
    })
    const store = useCredentialSessionStore()

    const pending = store.ensureDecryptedApiKey()
    await vi.waitFor(() => expect(store.showPassphraseModal).toBe(true))
    await store.submitPassphrase('내패스프레이즈')

    await expect(pending).resolves.toBe('sk-ant-y')
  })
})
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `cd moduyaksok-frontend && npx vitest run src/stores/credentialSession.spec.ts`
Expected: FAIL — `./credentialSession` 모듈이 없음

- [ ] **Step 3: `credentialSession.ts` 구현**

`moduyaksok-frontend/src/stores/credentialSession.ts` 신규 생성:

```ts
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import { decryptApiKey, deriveKeyFromBundle, type EncryptedBundle } from '../lib/credentialCrypto'

interface StoredBundle extends EncryptedBundle {
  provider: string
}

// 유도된 CryptoKey는 이 store(Pinia 기본 상태, persist 안 함)에만 메모리로 캐시한다.
// 새로고침하면 사라지고 패스프레이즈를 다시 물어본다 — auth.ts가 JWT를 localStorage에
// 안 두고 HttpOnly 쿠키만 쓰는 것과 같은 이유(모두약속 프런트 CLAUDE.md).
export const useCredentialSessionStore = defineStore('credentialSession', {
  state: () => ({
    bundle: null as StoredBundle | null,
    derivedKey: null as CryptoKey | null,
    showPassphraseModal: false,
    passphraseError: '',
    submitting: false,
    _resolve: null as ((value: string) => void) | null,
    _reject: null as ((err: Error) => void) | null,
  }),
  actions: {
    setBundle(bundle: StoredBundle) {
      this.bundle = bundle
    },
    clear() {
      this.bundle = null
      this.derivedKey = null
    },
    async ensureBundle(): Promise<StoredBundle> {
      if (this.bundle) return this.bundle
      const { data } = await api.get('/me/llm-credential')
      const bundle: StoredBundle = {
        provider: data.provider,
        ciphertext: data.ciphertext,
        salt: data.salt,
        iv: data.iv,
        kdfIterations: data.kdf_iterations,
      }
      this.bundle = bundle
      return bundle
    },
    async ensureDecryptedApiKey(): Promise<string> {
      const bundle = await this.ensureBundle()
      if (this.derivedKey) {
        return decryptApiKey(this.derivedKey, bundle)
      }
      return new Promise((resolve, reject) => {
        this._resolve = resolve
        this._reject = reject
        this.passphraseError = ''
        this.showPassphraseModal = true
      })
    },
    async submitPassphrase(passphrase: string) {
      if (!this.bundle) return
      this.submitting = true
      try {
        const key = await deriveKeyFromBundle(passphrase, this.bundle)
        const plaintext = await decryptApiKey(key, this.bundle)
        this.derivedKey = key
        this.showPassphraseModal = false
        this._resolve?.(plaintext)
        this._resolve = null
        this._reject = null
      } catch {
        this.passphraseError = '패스프레이즈가 틀렸어요'
      } finally {
        this.submitting = false
      }
    },
    cancelPassphrase() {
      this.showPassphraseModal = false
      this._reject?.(new Error('사용자가 패스프레이즈 입력을 취소했어요'))
      this._resolve = null
      this._reject = null
    },
  },
})
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `cd moduyaksok-frontend && npx vitest run src/stores/credentialSession.spec.ts`
Expected: PASS (3개 전부)

- [ ] **Step 5: `PassphraseModal.vue` 작성**

`moduyaksok-frontend/src/components/doodle/PassphraseModal.vue` 신규 생성 (기존 `LoginModal.vue`와 같은 패턴):

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useCredentialSessionStore } from '../../stores/credentialSession'
import DoodleModal from './DoodleModal.vue'
import DoodleInput from './DoodleInput.vue'
import DoodleButton from './DoodleButton.vue'

const store = useCredentialSessionStore()
const passphrase = ref('')

watch(
  () => store.showPassphraseModal,
  (open) => {
    if (!open) passphrase.value = ''
  },
)

async function submit() {
  if (!passphrase.value) return
  await store.submitPassphrase(passphrase.value)
}

function close() {
  store.cancelPassphrase()
}
</script>

<template>
  <DoodleModal :open="store.showPassphraseModal" title="패스프레이즈 입력" @close="close">
    <p class="mb-4 font-hand text-sm text-ink/60">
      등록한 API 키를 쓰려면 패스프레이즈가 필요해요. 서버에는 저장되지 않아요.
    </p>
    <DoodleInput
      v-model="passphrase"
      type="password"
      label="패스프레이즈"
      :error="store.passphraseError"
      @keyup.enter="submit"
    />
    <div class="mt-6 flex gap-3">
      <DoodleButton variant="ghost" :disabled="store.submitting" @click="close">취소</DoodleButton>
      <DoodleButton :disabled="store.submitting || !passphrase" @click="submit">
        {{ store.submitting ? '확인 중...' : '확인' }}
      </DoodleButton>
    </div>
  </DoodleModal>
</template>
```

- [ ] **Step 6: `App.vue`에 모달 마운트**

`moduyaksok-frontend/src/App.vue`의 import 목록:
```ts
import LoginModal from './components/doodle/LoginModal.vue'
```
바로 아래 추가:
```ts
import PassphraseModal from './components/doodle/PassphraseModal.vue'
```

템플릿의:
```html
  <LoginModal />
```
→
```html
  <LoginModal />
  <PassphraseModal />
```

- [ ] **Step 7: 프런트 타입체크/빌드 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공

- [ ] **Step 8: 커밋**

```bash
git add moduyaksok-frontend/src/stores/credentialSession.ts moduyaksok-frontend/src/stores/credentialSession.spec.ts moduyaksok-frontend/src/components/doodle/PassphraseModal.vue moduyaksok-frontend/src/App.vue
git commit -m "feat: 패스프레이즈 세션 캐시 store + 입력 모달 추가"
```

---

## Task 5: 프런트 — `ApiKeyEditView.vue` 등록 흐름 + `auth.ts` 번들 캐시

**Files:**
- Modify: `moduyaksok-frontend/src/views/settings/ApiKeyEditView.vue`
- Modify: `moduyaksok-frontend/src/views/settings/ApiKeyView.vue`
- Modify: `moduyaksok-frontend/src/stores/auth.ts`

**Interfaces:**
- Consumes: Task 3의 `encryptApiKey`/`maskKey`, Task 4의 `useCredentialSessionStore().setBundle`/`.clear`/`.ensureDecryptedApiKey()`.

- [ ] **Step 1: `ApiKeyEditView.vue` 재작성**

`moduyaksok-frontend/src/views/settings/ApiKeyEditView.vue` 전체를 다음으로 교체:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useCredentialSessionStore } from '../../stores/credentialSession'
import { api } from '../../lib/api'
import { encryptApiKey, maskKey } from '../../lib/credentialCrypto'
import DoodleButton from '../../components/doodle/DoodleButton.vue'
import DoodleInput from '../../components/doodle/DoodleInput.vue'

const route = useRoute()
const router = useRouter()
const store = useAuthStore()
const credentialSession = useCredentialSessionStore()

const key = ref('')
const passphrase = ref('')
const error = ref('')
const loading = ref(false)
const revealed = ref(false)

const providerNames = { openai: 'GPT', anthropic: 'Claude', upstage: 'Solar', google: 'Gemini' } as const
const placeholders = { openai: 'sk-...', anthropic: 'sk-ant-...', upstage: 'up_...', google: 'AIza...' } as const
const keyPatterns = {
  anthropic: /^sk-ant-[A-Za-z0-9_-]{20,}$/,
  openai: /^sk-[A-Za-z0-9_-]{20,}$/,
  upstage: /^up_[A-Za-z0-9]{20,}$/,
  google: /^AIza[A-Za-z0-9_-]{30,}$/,
} as const
const provider = store.apiKeyProvider ?? 'anthropic'
const providerName = providerNames[provider]
const placeholder = placeholders[provider]

async function save() {
  const trimmed = key.value.trim()
  if (!keyPatterns[provider].test(trimmed)) {
    error.value = `${providerName} API 키 형식이 아니에요`
    return
  }
  if (!passphrase.value) {
    error.value = '패스프레이즈를 입력해주세요'
    return
  }
  error.value = ''
  loading.value = true
  try {
    // 저장 전 짧은 검증 호출 — 평문은 이 요청에만 실리고 서버에 저장되지 않는다.
    await api.post('/me/llm-credential/verify', { provider, api_key: trimmed })

    const bundle = await encryptApiKey(passphrase.value, trimmed)
    const maskedKey = maskKey(trimmed)
    await api.post('/me/llm-credential', {
      provider,
      ciphertext: bundle.ciphertext,
      salt: bundle.salt,
      iv: bundle.iv,
      kdf_iterations: bundle.kdfIterations,
      masked_key: maskedKey,
    })

    credentialSession.setBundle({ provider, ...bundle })
    store.saveApiKey(maskedKey)
    router.push({ name: 'api-key-saved', query: route.query })
  } catch (err: any) {
    error.value = err.response?.data?.detail ?? '저장에 실패했어요. 다시 시도해주세요.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="notebook-bg flex min-h-dvh items-center justify-center px-6">
    <div class="w-full max-w-sm">
      <h1 class="mb-6 font-hand text-2xl text-ink">{{ providerName }} API 키 등록</h1>
      <div class="relative">
        <DoodleInput
          v-model="key"
          :type="revealed ? 'text' : 'password'"
          :placeholder="placeholder"
          label="API 키"
        />
        <button
          type="button"
          class="absolute right-3 top-[2.4rem] font-hand text-sm text-ink/50 hover:text-ink"
          @click="revealed = !revealed"
        >
          {{ revealed ? '숨기기' : '보기' }}
        </button>
      </div>
      <p class="mt-2 font-hand text-sm text-ink/50">발급받은 키를 붙여넣으세요. 저장 전 유효성을 확인해요.</p>

      <div class="mt-4">
        <DoodleInput v-model="passphrase" type="password" label="패스프레이즈" :error="error" />
        <p class="mt-2 font-hand text-sm text-ink/50">
          이 키를 암호화하는 데만 쓰여요. 서버에는 저장되지 않고, 잊어버리면 키를 다시 등록해야 해요.
        </p>
      </div>

      <div class="mt-6 flex gap-3">
        <DoodleButton variant="ghost" :disabled="loading" @click="router.back()">이전</DoodleButton>
        <DoodleButton :disabled="loading" @click="save">{{ loading ? '저장 중...' : '저장' }}</DoodleButton>
      </div>
    </div>
  </div>
</template>
```

(기존과 달리 `error`는 `key`가 아니라 `passphrase` 입력 아래로 옮겼다 — 형식 오류든 패스프레이즈 누락이든 저장 실패든 한 곳에 모아 보여준다.)

- [ ] **Step 2: `auth.ts`의 `syncApiKey`/`clearLocalSessionState`가 `credentialSession`도 같이 정리하도록 수정**

`moduyaksok-frontend/src/stores/auth.ts` 상단 import에 추가:
```ts
import { defineStore } from 'pinia'
import { api } from '../lib/api'
```
→
```ts
import { defineStore } from 'pinia'
import { api } from '../lib/api'
import { useCredentialSessionStore } from './credentialSession'
```

`clearLocalSessionState` 액션의:
```ts
    clearLocalSessionState() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      localStorage.removeItem('api_key_masked')
      localStorage.removeItem('api_key_provider')
      this.loggedIn = false
```
→
```ts
    clearLocalSessionState() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_name')
      localStorage.removeItem('api_key_masked')
      localStorage.removeItem('api_key_provider')
      useCredentialSessionStore().clear()
      this.loggedIn = false
```

(로그아웃/세션 만료 시 캐시된 유도키까지 같이 지워야 한다 — 안 그러면 다음 로그인 사용자가 이전 사용자의 메모리 캐시를 그대로 물려받을 위험이 있다.)

- [ ] **Step 3: `ApiKeyView.vue`의 "테스트"/"삭제" 버튼을 새 계약에 맞게 수정**

`moduyaksok-backend`의 `POST /me/llm-credential/test`가 Task 1에서 body로 평문 `api_key`를 요구하도록 바뀌었고(서버가 더 이상 스스로 복호화 못 함), 삭제 후에는 캐시된 번들/유도키도 같이 비워야 다음 등록이 이전 캐시를 잘못 재사용하지 않는다. `moduyaksok-frontend/src/views/settings/ApiKeyView.vue`의 import에 추가:

```ts
import { useAuthStore } from '../../stores/auth'
import { api } from '../../lib/api'
```
→
```ts
import { useAuthStore } from '../../stores/auth'
import { useCredentialSessionStore } from '../../stores/credentialSession'
import { api } from '../../lib/api'
```

```ts
const router = useRouter()
const store = useAuthStore()
```
→
```ts
const router = useRouter()
const store = useAuthStore()
const credentialSession = useCredentialSessionStore()
```

```ts
async function testKey() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await api.post('/me/llm-credential/test')
    testResult.value = { ok: true, message: `정상 작동해요 — 응답: "${data.reply}"` }
  } catch (err: any) {
    testResult.value = { ok: false, message: err.response?.data?.detail ?? '테스트에 실패했어요.' }
  } finally {
    testing.value = false
  }
}
```
→
```ts
async function testKey() {
  testing.value = true
  testResult.value = null
  try {
    const apiKey = await credentialSession.ensureDecryptedApiKey()
    const { data } = await api.post('/me/llm-credential/test', { api_key: apiKey })
    testResult.value = { ok: true, message: `정상 작동해요 — 응답: "${data.reply}"` }
  } catch (err: any) {
    testResult.value = { ok: false, message: err.response?.data?.detail ?? '테스트에 실패했어요.' }
  } finally {
    testing.value = false
  }
}
```

```ts
async function removeKey() {
  try {
    await api.delete('/me/llm-credential')
  } catch {
    // 이미 삭제됐거나 없는 경우도 로컬 상태는 정리한다.
  }
  store.clearApiKey()
}
```
→
```ts
async function removeKey() {
  try {
    await api.delete('/me/llm-credential')
  } catch {
    // 이미 삭제됐거나 없는 경우도 로컬 상태는 정리한다.
  }
  credentialSession.clear()
  store.clearApiKey()
}
```

- [ ] **Step 4: 프런트 타입체크/빌드 확인**

Run: `cd moduyaksok-frontend && npm run build`
Expected: 에러 없이 빌드 성공

- [ ] **Step 5: 커밋**

```bash
git add moduyaksok-frontend/src/views/settings/ApiKeyEditView.vue moduyaksok-frontend/src/views/settings/ApiKeyView.vue moduyaksok-frontend/src/stores/auth.ts
git commit -m "feat: API 키 등록/테스트/삭제 화면을 패스프레이즈 기반 로컬 암호화에 맞게 수정"
```

---

## Task 6: 프런트 — `stores/schedule.ts`가 로컬 복호화한 키를 요청에 실어 보내기

**Files:**
- Modify: `moduyaksok-frontend/src/stores/schedule.ts`
- Modify: `moduyaksok-frontend/src/stores/schedule.spec.ts`

**Interfaces:**
- Consumes: Task 4의 `useCredentialSessionStore().ensureDecryptedApiKey()`.

- [ ] **Step 1: `submitConditions`가 복호화한 키를 요청에 포함**

`moduyaksok-frontend/src/stores/schedule.ts` 상단 import에 추가:
```ts
import { api } from '../lib/api'
```
바로 아래:
```ts
import { useCredentialSessionStore } from './credentialSession'
```

`submitConditions` 액션의:
```ts
      const [startIso, endIso] = buildTimeRange(conditions.startTime, conditions.endTime)
      try {
        const { data } = await api.post('/schedules', {
          purpose: conditions.purpose,
          headcount: conditions.headcount,
          time_range: [startIso, endIso],
          region: conditions.region,
          liked_text: conditions.likedText,
          disliked_text: conditions.dislikedText,
          budget_per_person: conditions.budgetPerPerson,
        })
```
→
```ts
      const [startIso, endIso] = buildTimeRange(conditions.startTime, conditions.endTime)
      try {
        const apiKey = await useCredentialSessionStore().ensureDecryptedApiKey()
        const { data } = await api.post('/schedules', {
          purpose: conditions.purpose,
          headcount: conditions.headcount,
          time_range: [startIso, endIso],
          region: conditions.region,
          liked_text: conditions.likedText,
          disliked_text: conditions.dislikedText,
          budget_per_person: conditions.budgetPerPerson,
          api_key: apiKey,
        })
```

- [ ] **Step 2: `regenerateSchedule`이 복호화한 키를 요청에 포함**

```ts
    async regenerateSchedule() {
      if (!this.sessionId) return
      this.scheduleError = null
      try {
        const { data } = await api.post(`/schedules/${this.sessionId}/regenerate`)
```
→
```ts
    async regenerateSchedule() {
      if (!this.sessionId) return
      this.scheduleError = null
      try {
        const apiKey = await useCredentialSessionStore().ensureDecryptedApiKey()
        const { data } = await api.post(`/schedules/${this.sessionId}/regenerate`, {
          api_key: apiKey,
        })
```

- [ ] **Step 3: `previewCandidateReplacement`이 복호화한 키를 요청에 포함**

```ts
    async previewCandidateReplacement(
      candidateId: string,
      excludedPlaceIds: string[],
    ): Promise<{ previewId: string; candidate: Candidate }> {
      if (!this.sessionId) throw new Error('일정 세션이 없습니다.')
      const { data } = await api.post(
        `/schedules/${this.sessionId}/candidates/${candidateId}/preview`,
        { excluded_place_ids: excludedPlaceIds },
      )
```
→
```ts
    async previewCandidateReplacement(
      candidateId: string,
      excludedPlaceIds: string[],
    ): Promise<{ previewId: string; candidate: Candidate }> {
      if (!this.sessionId) throw new Error('일정 세션이 없습니다.')
      const apiKey = await useCredentialSessionStore().ensureDecryptedApiKey()
      const { data } = await api.post(
        `/schedules/${this.sessionId}/candidates/${candidateId}/preview`,
        { excluded_place_ids: excludedPlaceIds, api_key: apiKey },
      )
```

- [ ] **Step 4: 기존 vitest에 `credentialSession` mock 추가**

`moduyaksok-frontend/src/stores/schedule.spec.ts` 상단의:
```ts
vi.mock('../lib/api', () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))
```
바로 아래 추가:
```ts

vi.mock('./credentialSession', () => ({
  useCredentialSessionStore: () => ({
    ensureDecryptedApiKey: vi.fn().mockResolvedValue('sk-ant-fake-key'),
  }),
}))
```

- [ ] **Step 5: `previewCandidateReplacement` 테스트의 assertion 갱신**

```ts
    expect(apiPost).toHaveBeenNthCalledWith(1, '/schedules/session-1/candidates/A/preview', { excluded_place_ids: ['old-lunch'] })
```
→
```ts
    expect(apiPost).toHaveBeenNthCalledWith(1, '/schedules/session-1/candidates/A/preview', { excluded_place_ids: ['old-lunch'], api_key: 'sk-ant-fake-key' })
```

- [ ] **Step 6: 프런트 테스트 실행**

Run: `cd moduyaksok-frontend && npx vitest run src/stores/schedule.spec.ts`
Expected: PASS (전체)

- [ ] **Step 7: 프런트 전체 테스트 + 빌드 확인**

Run: `cd moduyaksok-frontend && npx vitest run && npm run build`
Expected: 전체 PASS, 빌드 성공

- [ ] **Step 8: 커밋**

```bash
git add moduyaksok-frontend/src/stores/schedule.ts moduyaksok-frontend/src/stores/schedule.spec.ts
git commit -m "feat: 스케줄 생성/재생성/후보 교체 요청에 로컬 복호화한 api_key 포함"
```

---

## Task 7: 문서 동기화

**Files:**
- Modify: `docs/기술설계_2026-08-06.md`
- Modify: `moduyaksok-backend/CLAUDE.md`
- Modify: `docs/API명세서_2026-08-06.md`
- Modify: `docs/ERD_2026-08-06.md`
- Modify: `moduyaksok-backend/README.md`
- Modify: `moduyaksok-backend/schedule.md`
- Modify: `moduyaksok-frontend/schedule.md`

- [ ] **Step 1: `docs/기술설계_2026-08-06.md` §3.4 갱신**

§3.4("키 저장 위치 논의") 끝(현재 "A안(완전 클라이언트 사이드)은 이 재사용이 안 되고 훨씬 큰 재작업." 문단 뒤, §3.5 앞)에 새 소절 추가:

```markdown
**2026-08-17, C안(PIN/패스프레이즈 기반 envelope encryption)으로 전환**: 실사용자가
생긴 뒤 위 트레이드오프를 다시 검토해 C안으로 결정했다. 상세 설계는
`docs/superpowers/specs/2026-08-17-byok-client-side-encryption-design.md` 참고.
서버는 이제 `CREDENTIAL_ENCRYPTION_KEY` 자체를 갖지 않는다 — 등록 시 사용자가
만드는 패스프레이즈로 브라우저(Web Crypto, PBKDF2→AES-GCM)가 암호화하고
암호문/salt/iv만 저장한다. 스케줄 생성처럼 파이프라인이 실제로 provider를
호출해야 하는 시점엔 클라이언트가 그때 로컬 복호화해 평문을 그 요청에만 실어
보내고, 서버는 처리 후 버린다. 기존에 서버 마스터키로 암호화돼 있던 행은 새
스킴으로 옮길 방법이 없어(패스프레이즈를 서버가 대신 만들 수 없음) 마이그레이션에서
삭제했고, 영향받는 사용자는 재등록이 필요하다.
```

- [ ] **Step 2: `moduyaksok-backend/CLAUDE.md`의 "BYOK 키 보안" 절 갱신**

"## BYOK 키 보안 — 알려진 한계, 지금은 구조 안 바꾸기로 함" 절 전체를 다음으로 교체:

```markdown
## BYOK 키 보안 — 클라이언트 패스프레이즈 암호화로 전환(2026-08-17)
- 서버는 더 이상 평문 API 키를 저장/복호화하지 못한다. 등록 시 사용자가 만드는
  패스프레이즈로 브라우저가 PBKDF2→AES-GCM 암호화하고, 서버는 암호문/salt/iv만
  저장한다(`app/models/llm_credential.py`). 상세 설계·이 결정에 이르기까지의
  검토는 `docs/기술설계_2026-08-06.md` §3.4, `docs/superpowers/specs/
  2026-08-17-byok-client-side-encryption-design.md` 참고.
- 파이프라인이 provider를 실제로 호출해야 하는 시점(스케줄 생성/재생성/후보
  교체, `app/routers/schedule.py`)엔 클라이언트가 로컬에서 복호화한 평문을 그
  요청의 `api_key` 필드로 보낸다 — 서버는 그 요청 처리 중에만 쓰고 저장하지
  않는다. 파이프라인 함수(`normalize_conditions` 등)가 이미 복호화된 평문
  `api_key: str`을 파라미터로 받는 설계는 그대로 유지되어, 이번 전환도
  `app/pipeline/*.py`는 건드리지 않았다.
- 패스프레이즈를 잊으면 서버가 대신 복구해줄 방법이 없다(구조상 당연) — 등록된
  키를 삭제하고 재등록하는 것만 유효한 경로.
```

- [ ] **Step 3: `docs/API명세서_2026-08-06.md`의 "2. API 키 (BYOK)" 절 갱신**

`POST /me/llm-credential` 항목을 새 계약(ciphertext/salt/iv/kdf_iterations/masked_key 받음, provider ping 안 함)으로 갱신하고, 신규 `POST /me/llm-credential/verify`(평문 받아 테스트만, 저장 안 함) 항목을 추가. `POST /me/llm-credential/test`가 body로 평문 `api_key`를 받는다는 점, `GET /me/llm-credential`이 이제 `ciphertext`/`salt`/`iv`/`kdf_iterations`도 함께 반환한다는 점을 명시. `POST /schedules`, `POST /schedules/{id}/regenerate`, `POST /schedules/{id}/candidates/{id}/preview`(교체) 요청 바디에 `api_key`(평문, 클라이언트가 실어 보냄) 필드가 추가됐다는 점도 각 항목에 반영.

- [ ] **Step 4: `docs/ERD_2026-08-06.md`의 `llm_credential` 항목 갱신**

`encrypted_key`의 의미가 "서버 Fernet 암호문"에서 "클라이언트 AES-GCM 암호문"으로 바뀌었다는 점, `salt`/`iv`/`kdf_iterations`/`masked_key` 컬럼이 추가됐다는 점을 반영.

- [ ] **Step 5: `moduyaksok-backend/README.md` 갱신**

"API 라우터" 표(69-70번 줄 근처)의 `credential.py` 행 — 엔드포인트 목록에 `POST /me/llm-credential/verify` 추가, 설명을 "평문 없이 암호문만 저장" 등으로 갱신.
"서비스" 표(79번 줄 근처)의 `credential.py` 행 삭제(서비스 자체를 지웠으므로).
`llm_credential.py`(109번 줄 근처) 모델 설명에 "클라이언트가 암호화한 값, 복호화는 서버가 못 함" 반영.

- [ ] **Step 6: 두 `schedule.md`에 이번 작업 반영**

`moduyaksok-backend/schedule.md`, `moduyaksok-frontend/schedule.md`에 이번 BYOK 클라이언트 암호화 전환 항목을 완료(✅)로 추가(완료 일시 포함).

- [ ] **Step 7: 커밋**

```bash
git add docs/기술설계_2026-08-06.md moduyaksok-backend/CLAUDE.md docs/API명세서_2026-08-06.md docs/ERD_2026-08-06.md moduyaksok-backend/README.md moduyaksok-backend/schedule.md moduyaksok-frontend/schedule.md
git commit -m "docs: BYOK 클라이언트 패스프레이즈 암호화 전환 문서 동기화"
```

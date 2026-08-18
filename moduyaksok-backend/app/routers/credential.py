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

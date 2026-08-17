# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST/GET/DELETE /me/llm-credential — 사용자 BYOK API 키 등록/조회/삭제
#              POST /me/llm-credential/test — 등록된 키로 provider에 핑 보내 유효성 확인
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, /me/llm-credential/test 추가
# 2026-08-12, 등록(save_credential) 시에도 저장 전에 ping_provider로 1회 테스트하고
#             성공해야만 저장하도록 변경 — 형식만 맞고 실제로는 무효/만료된 키가
#             그대로 등록되는 걸 막음
# ------------------------------------------------------------------
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationInfo, field_validator
from sqlmodel import Session, select

from app.db import get_session
from app.models.llm_credential import LLMCredential
from app.models.user import User
from app.services.auth import get_current_user
from app.services.credential import decrypt_key, encrypt_key, mask_key
from app.services.llm_ping import ping_provider

router = APIRouter()

Provider = Literal["anthropic", "openai", "upstage", "google"]

# 발급 기관이 공개한 키 접두사 기준. 완전한 형식 보증은 아니고 오탈자/다른 제공자
# 키 혼동을 막는 용도. 프런트(ApiKeyEditView.vue)에서 같은 패턴으로 먼저 걸러주지만,
# 요청을 직접 조작해 우회할 수 있으므로 여기서 다시 검증한다.
# google(Gemini)은 2026-08-17 추가 — "AIza" 접두사는 공개 문서 기준이고 실제 발급된
# 키로 검증은 안 해봤다(다른 provider 추가 때처럼 실제 키가 생기면 재확인할 것).
_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic": re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,}$"),  # Claude: "sk-ant-" 접두사
    "openai": re.compile(r"^sk-[A-Za-z0-9_-]{20,}$"),  # GPT: "sk-" 접두사
    "upstage": re.compile(r"^up_[A-Za-z0-9]{20,}$"),  # Solar: "up_" 접두사
    "google": re.compile(r"^AIza[A-Za-z0-9_-]{30,}$"),  # Gemini: "AIza" 접두사
}


class CredentialIn(BaseModel):
    # provider가 api_key보다 먼저 선언돼 있어야 아래 validator의 info.data에 채워진다
    # (pydantic은 필드를 선언 순서대로 검증하며, 이전 필드 값만 info.data로 넘겨줌).
    provider: Provider
    api_key: str

    @field_validator("api_key")
    @classmethod
    def validate_key_format(cls, v: str, info: ValidationInfo) -> str:
        provider = info.data.get("provider")  # 위 provider 필드의 검증된 값
        pattern = _KEY_PATTERNS.get(provider)
        if pattern and not pattern.match(v):
            raise ValueError(f"{provider} API 키 형식이 아닙니다.")
        return v


class CredentialOut(BaseModel):
    provider: str
    masked_key: str


class CredentialTestOut(BaseModel):
    reply: str


def _get_credential(session: Session, user_id) -> LLMCredential | None:
    return session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()


@router.post("/me/llm-credential", response_model=CredentialOut)
def save_credential(
    body: CredentialIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialOut:
    try:
        ping_provider(body.provider, body.api_key)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"API 키 테스트에 실패했어요: {exc}"
        ) from exc

    existing = _get_credential(session, current_user.id)
    encrypted = encrypt_key(body.api_key)
    verified_at = datetime.utcnow()
    if existing is None:
        existing = LLMCredential(
            user_id=current_user.id,
            provider=body.provider,
            encrypted_key=encrypted,
            verified_at=verified_at,
        )
    else:
        existing.provider = body.provider
        existing.encrypted_key = encrypted
        existing.verified_at = verified_at
    session.add(existing)
    session.commit()
    return CredentialOut(provider=body.provider, masked_key=mask_key(body.api_key))


@router.get("/me/llm-credential", response_model=CredentialOut)
def read_credential(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialOut:
    credential = _get_credential(session, current_user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    masked_key = mask_key(decrypt_key(credential.encrypted_key))
    return CredentialOut(provider=credential.provider, masked_key=masked_key)


@router.post("/me/llm-credential/test", response_model=CredentialTestOut)
def test_credential(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CredentialTestOut:
    credential = _get_credential(session, current_user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    raw_key = decrypt_key(credential.encrypted_key)
    try:
        reply = ping_provider(credential.provider, raw_key)
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

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 사용자별 LLM API 키(BYOK) 저장 테이블 정의
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, provider 기본값 제거, 등록 시 Claude/GPT 중 선택 필수로 변경
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class LLMCredential(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id", unique=True)
    provider: str  # "anthropic" | "openai" — API 요청 스키마(Pydantic Literal)에서 값 제한
    encrypted_key: bytes
    verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

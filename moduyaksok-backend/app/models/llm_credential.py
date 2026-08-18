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

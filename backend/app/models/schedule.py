# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 일정 세션, 피드백, 공유 링크 테이블 정의
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, 개발 DB를 Postgres(docker)로 고정, JSON 컬럼을 JSONB로 변경
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ScheduleSession(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id")
    conditions: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    candidates: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackMessage(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedulesession.id")
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ShareLink(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedulesession.id")
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

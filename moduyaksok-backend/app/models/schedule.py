# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 일정 세션, 피드백, 공유 링크 테이블 정의
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-06, 개발 DB를 Postgres(docker)로 고정, JSON 컬럼을 JSONB로 변경
# 2026-08-06, __tablename__ 명시 (SQLModel 기본 테이블명이 ERD의 snake_case와 불일치해서 수정)
# 2026-08-07, status 값을 "draft"/"confirmed"로 제약 — DB에는 CHECK 제약 추가
#             (마이그레이션 f4f8459f626b). SQLModel(이 버전)은 table=True 모델의
#             컬럼에 Literal을 못 붙여서 필드 자체는 str로 두고, ScheduleStatus
#             타입 별칭을 남겨서 나중에 라우터 Pydantic 스키마(테이블 아닌 곳)에서
#             쓰게 한다. draft→confirmed 전이는 한 방향만 허용 — POST
#             /schedules/{id}/confirm 라우터 구현 시 이미 confirmed인 세션은
#             재확정 못 하게 막을 것 (아직 라우터 자체가 없어 미구현).
# 2026-08-10, confirmed_candidate_id 컬럼 추가 — GET /share/{slug}가 3개 후보 중
#             확정된 하나를 찾으려면 어느 candidate_id가 확정됐는지 저장해야 함
#             (기존엔 status만 confirmed로 바뀌고 어떤 후보인지는 저장 안 됐음).
# ------------------------------------------------------------------
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

ScheduleStatus = Literal["draft", "confirmed"]


class ScheduleSession(SQLModel, table=True):
    __tablename__ = "schedule_session"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id")
    conditions: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    candidates: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = "draft"  # 허용값은 ScheduleStatus 참고, 실제 제약은 DB CHECK가 건다
    # confirm된 후보의 candidate_id("A"/"B"/"C"). draft 상태에선 항상 None —
    # GET /share/{slug}가 3개 후보 중 어느 걸 공개할지 이 값으로 찾는다.
    confirmed_candidate_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackMessage(SQLModel, table=True):
    __tablename__ = "feedback_message"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedule_session.id")
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ShareLink(SQLModel, table=True):
    __tablename__ = "share_link"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedule_session.id")
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

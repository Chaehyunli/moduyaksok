# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 사용자 테이블 정의 (Google 로그인 기반)
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    google_id: str = Field(unique=True, index=True)
    email: str
    name: str | None = None
    picture_url: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

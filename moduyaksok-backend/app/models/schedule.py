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
# 2026-08-11, SchedulePlacePool 추가 — 네이버 지역검색 결과(place_candidates,
#             지역당 최소 50개 목표)를 세션마다 저장해서, 나중에 피드백으로 일정을
#             수정할 때 이미 검색한 태그는 네이버 API를 다시 안 부르고(새로 등장한
#             태그만 추가 검색) 재사용하기 위함. 처음엔 이 컬럼들(place_pool,
#             searched_liked_tags, searched_disliked_tags)을 ScheduleSession에
#             바로 얹는 안을 검토했는데, ScheduleSession은 상태 전이(draft/confirmed)
#             시점에만 바뀌는 "핵심 엔티티"이고 place_pool은 피드백이 올 때마다
#             갱신되는 "생성용 내부 상태"라 갱신 빈도·읽는 이유가 전혀 다르다는
#             지적(사용자)에 따라 별도 테이블로 분리 — 일정 조회/공유처럼 자주
#             일어나는 가벼운 읽기가 이 큰 JSONB 블록을 매번 같이 들고 다닐
#             필요가 없다. session_id에 unique 제약을 걸어 1:1 관계를 강제한다.
#             candidates(최종 3개 후보)는 그대로 ScheduleSession에 남겨둔다 —
#             이건 사용자가 실제로 조회/확정하는 대상이라 place_pool과 달리
#             "핵심 엔티티"의 일부로 취급한다.
# 2026-08-15, ScheduleRequiredPlace에 is_custom/mapx/mapy 추가(마이그레이션
#             65e23b502964) — 사용자가 검색해서 직접 고른 장소(표준 카테고리·
#             태그 검색과 무관)를 구분하고, 재생성 때마다 새로 뜨는
#             place_candidates에 원본 좌표 그대로 주입할 수 있게 한다. 일반
#             필수 장소는 매번 다시 검색되므로 mapx/mapy가 비어 있어도 된다.
# 2026-08-15, FeedbackMessage 제거(마이그레이션 f1a2b3c4d5e6) — 실제로 어디서도
#             insert되지 않는 미구현 기능의 테이블이라 삭제.
# ------------------------------------------------------------------
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

ScheduleStatus = Literal["draft", "confirmed"]


class ScheduleSession(SQLModel, table=True):
    __tablename__ = "schedule_session"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    user_id: UUID = Field(foreign_key="user.id")
    conditions: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    # Step1이 한 번 정규화한 조건을 그대로 보관한다. 필수 장소를 추가해 다시
    # 생성할 때 Step1을 재호출하면 같은 원문에서도 태그가 달라질 수 있으므로,
    # 재생성은 이 스냅샷을 써서 기존 조건을 정확히 유지한다.
    normalized_conditions: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    candidates: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    status: str = "draft"  # 허용값은 ScheduleStatus 참고, 실제 제약은 DB CHECK가 건다
    # confirm된 후보의 candidate_id("A"/"B"/"C"). draft 상태에선 항상 None —
    # GET /share/{slug}가 3개 후보 중 어느 걸 공개할지 이 값으로 찾는다.
    confirmed_candidate_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SchedulePlacePool(SQLModel, table=True):
    __tablename__ = "schedule_place_pool"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    # 1:1 — 세션 하나당 place_pool 하나만 누적한다(unique 제약).
    session_id: UUID = Field(foreign_key="schedule_session.id", unique=True)
    # naver_local_search.search_places_for_region()이 반환한 병합 결과(title 기준
    # 중복 제거된 place dict 목록) 그대로. {"places": [...]} 형태로 감싸는 건
    # ScheduleSession.candidates와 같은 관례(app/routers/schedule.py 참고).
    places: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    # 검색 질의별 결과 스냅샷. ``places``는 Step2에 넘긴 안전한 병합 목록만 갖지만,
    # 이 필드는 좋아요/싫어요/카테고리별 원본 결과를 보존한다. 특히 싫어요 태그와
    # 겹쳐 Step2에서 제거된 장소도 여기에는 남겨 사용자가 제외 근거를 확인하고,
    # 추후 피드백 검색 시 이미 조회한 결과를 재사용할 수 있다.
    search_groups: dict = Field(default_factory=dict, sa_column=Column(JSONB))
    # 지금까지 태그 검색을 실제로 호출한 verifiable 태그 목록 — 나중에 피드백으로
    # 새 태그가 추가되면 이 목록에 없는 태그만 추가 검색하면 된다(피드백 엔드포인트
    # 자체는 아직 미구현, schedule.md 참고).
    searched_liked_tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    searched_disliked_tags: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ScheduleRequiredPlace(SQLModel, table=True):
    """사용자가 확정 전 일정에 반드시 넣어달라고 고른 장소.

    검색 후보 풀의 장소 ID만 저장하면 이후 검색 결과를 누적할 때 원래 표시 정보가
    사라질 수 있다. 그래서 선택 시점의 최소 스냅샷도 함께 보관해, 재방문/새로고침
    뒤에도 사용자가 무엇을 고정했는지 항상 확인할 수 있게 한다.
    """

    __tablename__ = "schedule_required_place"
    __table_args__ = (
        UniqueConstraint("session_id", "place_id", name="uq_schedule_required_place_session_place"),
    )

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedule_session.id")
    # 네이버 place id가 모든 검색 결과에 안정적으로 오지 않으므로, 이름+도로명
    # 주소에서 만든 결정론적 SHA-256 식별자(services.naver_local_search.place_id_for).
    place_id: str = Field(index=True)
    name: str
    category: str = ""
    address: str = ""
    map_url: str = ""
    # 사용자가 표준 카테고리·태그 검색과 무관하게 직접 이름으로 검색해서 고른
    # 장소인지 — 재생성 때 place_candidates 주입 여부를 가른다.
    is_custom: bool = False
    # 네이버 지역검색 원본 좌표(×1e7 문자열, naver_local_search.py의 mapx/mapy와
    # 동일 형식) — is_custom 장소만 채운다. 일반 필수 장소는 재생성마다 새
    # place_candidates에서 place_id로 다시 찾아지므로 비워둔다.
    mapx: str | None = None
    mapy: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ShareLink(SQLModel, table=True):
    __tablename__ = "share_link"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    session_id: UUID = Field(foreign_key="schedule_session.id")
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : AI 파이프라인 단계 간 입출력 스키마 (docs/기술설계_2026-08-06.md §4,
#              docs/API명세서_2026-08-06.md POST /schedules 기준)
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# ── Step 1. 조건 정규화 (normalize_conditions) 출력 ────────────────────────


class NormalizedConditions(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
    liked_tags: list[str]
    disliked_tags: list[str]
    budget_per_person: int


# ── Step 2. 후보 생성 (generate_candidates) 출력 ───────────────────────────


class ActivityDraft(BaseModel):
    name: str
    category: str
    start_time: str
    end_time: str
    price_range_per_person: tuple[int, int]


class CandidateDraft(BaseModel):
    title: str
    activities: list[ActivityDraft]
    rationale: str  # Step 4에서 랭킹 근거로 사용


# ── Step 3. 이동 동선 보강 (enrich_routes) 출력 ────────────────────────────


class RouteSegment(BaseModel):
    from_order: int
    to_order: int
    mode: Literal["walk", "transit", "car"]
    duration_minutes: int
    fare_krw: int


class EnrichedCandidate(BaseModel):
    draft: CandidateDraft
    routes: list[RouteSegment]
    feasibility_warning: str | None = None


# ── Step 4. 검증·병합·랭킹 (synthesize_and_validate) 출력 = 최종 응답 ─────────


class Activity(BaseModel):
    order: int
    name: str
    category: str
    address: str
    start_time: str
    end_time: str
    price_range_per_person: tuple[int, int]
    operating_hours: str
    phone: str | None = None
    info_needs_check: bool = False


class Candidate(BaseModel):
    candidate_id: str
    title: str
    why_recommended: str
    activities: list[Activity]
    routes: list[RouteSegment]
    feasibility_warning: str | None = None


class ScheduleResponse(BaseModel):
    session_id: str
    candidates: list[Candidate]


class InfeasibleResponse(BaseModel):
    detail: str
    reason: str
    adjustable_conditions: list[str]

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
#
# 구간마다 교통수단 옵션을 여러 개 보여주고 사용자가 고르게 한다 (도보/버스/택시
# 등 하나로 자동 선택하지 않음 — 사용자가 원치 않는 교통편이 자동으로 박히면
# UX가 깨진다는 판단). recommended_mode는 기본 선택값(예: 최단 소요시간)일 뿐,
# 최종 선택은 프런트에서 사용자가 바꿀 수 있다.
#
# 조회 시각은 각 구간 직전 활동의 end_time을 출발 시각으로 넣어야 한다 — "지금
# 시각" 기준으로 조회하면 막차 끊긴 늦은 시간대 일정에서 엉뚱한 결과가 나온다.
# 특정 시간대에 옵션이 아예 없으면(막차 없음 등) options가 비거나 줄어들 수 있고,
# 그 경우 feasibility_warning으로 올린다.


class RouteOption(BaseModel):
    mode: Literal["walk", "transit", "car"]
    duration_minutes: int
    fare_krw: int


class RouteSegment(BaseModel):
    from_order: int
    to_order: int
    options: list[RouteOption]
    recommended_mode: Literal["walk", "transit", "car"]


class EnrichedCandidate(BaseModel):
    draft: CandidateDraft
    routes: list[RouteSegment]
    feasibility_warning: str | None = None


# ── Step 4. 검증·병합 (synthesize_and_validate) 출력 = 최종 응답 ──────────────
# 랭킹 없음 — 3개는 서로 다른 관점으로 만든 동등한 선택지라 rank 필드가 없다.
# candidate_id도 순위를 암시하는 숫자 대신 "A"/"B"/"C" 문자를 쓴다.


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

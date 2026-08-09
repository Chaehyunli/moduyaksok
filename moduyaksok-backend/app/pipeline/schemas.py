# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : AI 파이프라인 단계 간 입출력 스키마 (docs/기술설계_2026-08-06.md §4,
#              docs/API명세서_2026-08-06.md POST /schedules 기준)
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, liked_tags/disliked_tags를 list[str] -> list[PreferenceTag]로 변경.
#             "해산물"처럼 장소 카테고리로 확인 가능한 태그와 "사람 많은 곳"처럼
#             확인할 데이터가 없는 주관적 태그를 구분해서 Step2에 넘겨야, Step2가
#             전자는 확실히 보장(필터)하고 후자는 참고만(소프트 신호) 하게 만들 수 있음.
# 2026-08-09, region: str -> regions: list[str]. 사용자가 시/도만(예: "서울") 또는
#             시/도+세부지역을 최대 3개까지 조합해서 넣을 수 있게 프런트가 바뀌는데
#             맞춰 스키마도 리스트로 변경. Step1은 그대로 통과만 시키므로 값 조립
#             로직은 안 바뀜. 개수 제한(최대 3, 시/도만 최대 1)·포함관계 중복 제거는
#             validate_regions()가 생성 시점에 강제 — 프런트 검증과 같은 규칙을
#             백엔드에서도 재검증(요청 직접 조작 대비).
# 2026-08-09, PlaceSelectionDraft/CandidateSelectionDraft 추가 — Step2를 "장소
#             선택"(LLM)과 "시간 배정"(결정론적 계산)으로 분리하는 실험. 하나의
#             LLM 호출에 환각 방지·verifiable 하드/소프트·예산·반복방지·시간
#             겹침 없음·관점 반영을 다 시키니 HIGH 티어로도 일부 케이스에서
#             못 버티는 걸 실측 확인(generate_step2.py 변경 이력 참고) — 시간
#             배정을 코드로 떼어내서 LLM 부담을 줄여본다.
# ------------------------------------------------------------------
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

# ── Step 1. 조건 정규화 (normalize_conditions) 출력 ────────────────────────


class PreferenceTag(BaseModel):
    tag: str
    # place_candidates의 카테고리/이름 같은 데이터로 확인 가능한 객관적 태그면 True
    # (예: "해산물", "파스타", "스타벅스"). 분위기/혼잡도처럼 확인할 데이터가 없는
    # 주관적 태그면 False (예: "사람 많은 곳", "조용한 분위기"). Step2가 이 값으로
    # "반드시 지킬 것"과 "참고만 할 것"을 구분한다.
    verifiable: bool


class NormalizedConditions(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    # 총 최대 3개, 그중 "시/도만(세부지역 없음)"인 항목은 최대 1개까지만 —
    # validate_regions()가 강제. 여러 지역 각각에 대해 네이버 지역검색을 호출해
    # 병합한다(app/services/naver_local_search.py의 search_places_for_regions(),
    # 이 함수를 부를 POST /schedules 라우터는 아직 없음).
    regions: list[str]

    # 프런트(ConditionWizardView)에서 같은 규칙으로 먼저 걸러주지만, 요청을 직접
    # 조작해 우회할 수 있으므로 여기서 다시 검증한다(app/routers/credential.py의
    # API 키 형식 검증과 같은 패턴, 2026-08-09).
    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("regions는 최소 1개 이상이어야 합니다.")

        def has_district(region: str) -> bool:
            return len(region.split()) >= 2

        # 포함관계 중복 제거: 같은 시/도를 세부지역 없이(전체) 넣은 게 있으면
        # 그 시/도의 세부지역 항목은 포함관계상 중복이므로 제거한다.
        broad_provinces = {r for r in v if not has_district(r)}
        deduped = [r for r in v if not has_district(r) or r.split()[0] not in broad_provinces]

        broad_count = sum(1 for r in deduped if not has_district(r))
        if len(deduped) > 3:
            raise ValueError(f"regions는 최대 3개까지만 가능합니다 (받은 개수: {len(deduped)}).")
        if broad_count > 1:
            raise ValueError(
                f"세부지역 없이 시/도만 넣은 지역은 최대 1개까지만 가능합니다 "
                f"(받은 개수: {broad_count})."
            )
        return deduped

    liked_tags: list[PreferenceTag]
    disliked_tags: list[PreferenceTag]
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


# generate_step2._call_all_perspectives_sync()가 LLM에서 받는 "1단계" 출력 —
# 장소 선택·예산·취향 판단만 LLM이 하고, 시간 배정(start_time/end_time)은
# LLM 출력에 안 넣는다. 겹침 없는 시간 배정은 결정론적 계산 문제라 LLM이
# "환각 방지 + verifiable 하드/소프트 + 예산 + 반복방지 + 시간 겹침 없음 +
# 관점 반영"을 한 번에 다 하게 시키면 못 버틴다는 게 실측으로 확인됨(2026-08-09,
# generate_step2.py 변경 이력 참고) — 시간 배정은 떼어내서
# generate_step2._schedule_places()가 결정론적으로 채운다.
class PlaceSelectionDraft(BaseModel):
    name: str
    category: str
    price_range_per_person: tuple[int, int]


class CandidateSelectionDraft(BaseModel):
    title: str
    places: list[PlaceSelectionDraft]
    rationale: str


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

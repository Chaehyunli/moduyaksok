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
# 2026-08-10, 파이프라인 실행 순서를 Step1→2→3→4(3=검증·병합, 4=이동 동선 보강)로
#             재설계하면서 이 파일의 섹션 순서·번호도 실행 순서에 맞게 재배치 —
#             synthesize_and_validate 출력(Activity/Candidate/ScheduleResponse)이
#             "Step 3"으로, enrich_routes 출력(RouteOption/RouteSegment/
#             EnrichedCandidate)이 "Step 4"로 라벨이 바뀌었다(함수/파일명도 동일하게
#             synthesize_step4.py -> synthesize_step3.py, enrich_step3.py ->
#             enrich_step4.py로 변경). Candidate가 RouteSegment를 참조하는데 물리적
#             선언 순서는 반대가 되어 `from __future__ import annotations`로 지연
#             평가를 켜서 순서 문제를 없앴다. `Candidate.routes`는 이제 Step3 직후
#             (아직 경로 없음)와 Step4 이후(경로 있음) 둘 다를 표현해야 해서
#             `= []` 기본값을 추가했다.
# 2026-08-10, RouteOption/RouteSegment 확장 — ODsay가 대중교통 안에서도 경로를
#             여러 개(지하철만/버스만/환승조합) 한 응답에 같이 준다는 게 실측으로
#             확인됐는데 그중 1개만 쓰고 있던 걸 바로잡음. RouteOption에
#             option_id/transfer_count/description 추가, RouteSegment의
#             recommended_mode를 recommended_option_id + selected_option_id로
#             분리 — 사용자가 고른 옵션을 별도로 저장해서 언제든 다시 바꿀 수
#             있게 한다(초기값은 recommended와 동일).
# ------------------------------------------------------------------
from __future__ import annotations

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
    # place_candidates(네이버 지역검색 원본)에서 결정론적으로 부착 — LLM 출력이
    # 아니다(place_candidates에 없는 환각 장소면 빈 값/None으로 남는다). Step2의
    # 좌표 기반 버퍼 추정(travel_estimate.py)과 Step4의 ODsay 호출 둘 다 이 값을
    # 쓴다. mapx/mapy는 WGS84 경도/위도 × 10^7이라 변환 없이 /1e7만 하면 된다
    # (실측 확인, 2026-08-10).
    address: str = ""
    lat: float | None = None
    lng: float | None = None


class CandidateDraft(BaseModel):
    title: str
    activities: list[ActivityDraft]
    rationale: str  # Step 3에서 랭킹 근거로 사용


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


# ── Step 3. 검증·병합 (synthesize_and_validate) 출력 ────────────────────────
# 랭킹 없음 — 3개는 서로 다른 관점으로 만든 동등한 선택지라 rank 필드가 없다.
# candidate_id도 순위를 암시하는 숫자 대신 "A"/"B"/"C" 문자를 쓴다.
#
# 이 시점엔 아직 이동 경로가 없다(Step4가 사용자 선택 이후에 채운다) —
# `Candidate.routes`는 그래서 빈 리스트가 기본값이다. TODO: synthesize_step3.py를
# 실제로 구현할 때, 입력을 EnrichedCandidate(경로 포함, 예전 가정)가 아니라
# CandidateDraft 리스트로 받고 여기서 ActivityDraft -> Activity 변환(order 부여,
# operating_hours/phone 채우기 등)까지 하도록 시그니처를 맞출 것.


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
    routes: list[RouteSegment] = []
    feasibility_warning: str | None = None


class ScheduleResponse(BaseModel):
    session_id: str
    candidates: list[Candidate]


class InfeasibleResponse(BaseModel):
    detail: str
    reason: str
    adjustable_conditions: list[str]


# ── Step 4. 이동 동선 보강 (enrich_routes) 출력 ────────────────────────────
#
# 구간마다 조회된 이동 옵션을 하나로 추려서 반환하지 않고 전부 담아 사용자가
# 고르게 한다 — 처음엔 도보/대중교통/차량 "모드" 단위로만 여러 개였는데, ODsay가
# 대중교통 안에서도 여러 실제 경로(지하철만/버스만/환승조합)를 이미 한 응답에
# 같이 준다는 게 실측으로 확인돼(2026-08-10) 그 경로들도 버리지 않고 다 담는다
# — 그중 하나만 골라 쓰는 지금 방식이면 "네이버 지도처럼 여러 교통편 후보를
# 보여주고 싶다"는 요구를 못 채움. `option_id`로 각 옵션을 구분한다
# (예: "walk", "transit-0", "transit-1").
#
# `recommended_option_id`는 Step4가 처음 계산할 때의 기본값(예: 최단 소요시간)이고,
# `selected_option_id`는 사용자가 실제로 확정한 값 — 초기값은 recommended와
# 같지만 언제든 사용자가 다른 옵션으로 바꿀 수 있고, 그 변경이 이 필드에
# 저장된다(프런트가 바뀐 값을 다시 보여줄 수 있게). 재조정(reconcile_schedule)에
# 쓰는 소요시간도 selected_option_id 기준이어야 한다 — 사용자가 고른 옵션이
# 아니라 recommended 기준으로 시간을 재조정하면 화면에 보여주는 시간과
# 실제 선택이 어긋난다.
#
# 사용자가 Step3 결과(경로 없는 후보 3개) 중 하나를 고른 뒤에만 실행 — 나머지
# 후보에는 호출하지 않아 ODsay Basic(일 1,000건) 호출을 아낀다.


class RouteOption(BaseModel):
    option_id: str
    mode: Literal["walk", "transit", "car"]
    duration_minutes: int
    fare_krw: int
    transfer_count: int = 0  # 환승 횟수. walk/car는 항상 0
    description: str = ""  # 사람이 읽을 경로 요약(예: "강남 -> 교대 -> 시청, 2호선")


class RouteSegment(BaseModel):
    from_order: int
    to_order: int
    options: list[RouteOption]
    recommended_option_id: str
    selected_option_id: str


class EnrichedCandidate(BaseModel):
    draft: CandidateDraft
    routes: list[RouteSegment]
    feasibility_warning: str | None = None

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
# 2026-08-10, Step3(synthesize_and_validate) 구현 시작하며 Activity에 map_url
#             추가 — 영업시간 자동 확인을 포기하는 대신(operating_hours는 항상
#             빈 문자열, info_needs_check=True) naver_map_url.build_naver_map_url()
#             로 만든 링크를 얹어 사용자가 직접 확인하게 유도하는데, 그 링크를
#             둘 필드가 기존엔 없었다.
# 2026-08-10, 라우터(app/routers/schedule.py) 구현하며 발견: enrich_routes()가
#             CandidateDraft를 받아 EnrichedCandidate(draft 감싼 별도 타입)를
#             반환했는데, 실제로 사용자가 고르고 DB에 저장되는 건 Step3가 만든
#             Candidate다 — Candidate.routes/feasibility_warning은 애초에 Step4가
#             나중에 채우라고 만들어둔 필드였는데 정작 enrich_routes()가 그걸 안
#             썼다. Activity에 lat/lng 추가(ActivityDraft에서 그대로 복사)하고
#             enrich_routes()가 Candidate를 직접 받고 돌려주게 고쳐서 EnrichedCandidate
#             삭제 — 중간에 다른 타입으로 갈아탈 이유가 없었다.
# 2026-08-10, RouteOption에 path 필드 추가(list[tuple[float, float]], 기본값 빈
#             리스트). NCP Maps Directions 5 API가 반환하는 [lng, lat] 쌍을 (lat,
#             lng) 튜플로 변환해서 프런트(Naver Maps JS SDK) 지도에 직접 그릴 수
#             있게 한다 — 지도가 LatLng(lat, lng) 순서를 쓰므로 백엔드에서 미리
#             순서를 맞춰 보낸다.
# 2026-08-10, ScheduleResponse에 share_slug 추가(전체 브랜치 리뷰 Finding 1).
#             확정 응답을 새로고침/네트워크 문제로 놓쳐도 GET /schedules/{id}로
#             다시 slug를 찾을 수 있게 한다 — 값이 없으면(미확정) None.
# 2026-08-11, "와플" 태그가 있는데 실제로 와플을 안 파는 카페가 verifiable=true로
#             하드 반영되는 정밀도 문제(2026-08-10 미해결 설계 질문, AI파이프라인_
#             Step별_설계 참고) 해결책으로 태그 전용 검색을 도입하며 두 가지 추가:
#             (1) ActivityDraft.matched_tag — 이 장소가 어느 liked_tags 태그
#             검색에서 나왔는지 결정론적으로 기록, Step3가 "같은 태그 중복 반영"을
#             판단하는 근거로 씀. (2) NormalizedConditions.cap_verifiable_tags —
#             태그 검색이 지역 확장과 곱해지면 호출량이 커지므로 verifiable 태그를
#             좋아하는/싫어하는 것 각각 최대 3개로 제한(Step1 프롬프트가 우선
#             지시하고, 이 validator는 방어용 하한선).
# 2026-08-11, 관점 3개가 비슷한 후보를 만드는 문제(같은 태그 매칭 장소를 여러
#             관점이 동시에 욕심냄) + 식사(점심/저녁) 없이 디저트만으로 채워지는
#             문제, 두 가지를 같이 해소하며 ActivityDraft.source_category 추가 —
#             matched_tag와 같은 방식으로, 이 장소가 카테고리 검색(맛집/카페/
#             액티비티/문화시설) 중 어느 쿼리에서 나왔는지 결정론적으로 기록.
#             Step3가 "점심/저녁 시간대에 맛집 카테고리 활동이 있는지" 판단하는
#             근거로 쓴다.
# 2026-08-11(2차), regions: list[str] -> region: str로 축소, MAX_VERIFIABLE_TAGS
#             3 -> 5로 상향. 네이버 지역검색 API가 display(1~5)/start(사실상 고정)
#             둘 다 좁아서 여러 지역을 받아봐야 지역당 결과만 희석된다는 걸 문서로
#             확인(사용자) — 세부지역 필수 단일 지역 + 카테고리/태그 쿼리 팬아웃
#             (naver_local_search.py)으로 지역당 최소 50개 후보를 모으는 쪽으로
#             방향 전환. 이 축소로 지역 확장(app.services.regions.expand_broad_region)
#             호출량 여유가 생겨 verifiable 태그 상한도 함께 올렸다.
# ------------------------------------------------------------------
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

# liked_tags/disliked_tags 중 verifiable=true인 태그 하나당 naver_local_search가
# "{region} {tag}" 검색을 추가로 호출한다(2026-08-11 설계) — 자유텍스트라 개수
# 제한이 없으면 호출량이 감당 안 되게 커진다. Step1이 좋아하는/싫어하는 것 각각
# 최대 이 개수까지만, 사용자가 더 중요하게 언급한 순서로 남기도록 프롬프트로
# 지시하고(normalize_step1.py), 이 값은 그 지시를 LLM이 안 지켰을 때의 방어용
# 상한이다. 2026-08-11(2차): region을 세부지역 필수 단일 값으로 좁히면서(지역
# 확장이 사라져 호출량 여유가 생김) + 카테고리도 세분화하면서, 태그 커버리지를
# 넓히려고 3 -> 5로 상향(사용자 결정).
MAX_VERIFIABLE_TAGS = 5

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
    # 세부지역까지 포함한 단일 지역 하나만 받는다(예: "서울 강남") — 2026-08-11(2차)
    # 결정. 예전엔 최대 3개까지 조합해서 받았는데, 네이버 지역검색 API가 display를
    # 1~5로, start를 사실상 고정으로 제한해서(NAVER API HUB 공식 문서로 확인)
    # 지역을 여러 개로 쪼갤수록 지역당 결과가 더 희석되는 역효과가 났다. 대신
    # 지역 하나에 카테고리·태그 쿼리를 최대한 팬아웃해서(naver_local_search.py)
    # 지역당 후보 풀을 최소 50개 이상 확보하는 쪽으로 방향을 바꿨다 — 여러 지역
    # 지원을 포기한 게 의도한 흐름(사용자 결정).
    region: str

    # 프런트(ConditionWizardView)에서 같은 규칙으로 먼저 걸러주지만, 요청을 직접
    # 조작해 우회할 수 있으므로 여기서 다시 검증한다(app/routers/credential.py의
    # API 키 형식 검증과 같은 패턴, 2026-08-09).
    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        if len(v.split()) < 2:
            raise ValueError(
                f"region은 세부지역까지 포함해야 합니다 (예: '서울 강남'). 받은 값: {v!r}"
            )
        return v

    liked_tags: list[PreferenceTag]
    disliked_tags: list[PreferenceTag]
    budget_per_person: int

    # Step1 프롬프트가 "verifiable=true는 좋아하는/싫어하는 것 각각 최대 3개,
    # 중요한 순서로"를 지시하지만(normalize_step1.py), LLM이 안 지킬 경우를 대비한
    # 방어용 상한 — validate_regions()와 같은 이유로 생성 시점에 재검증한다.
    # regions와 달리 위반이어도 ValueError를 던지지 않고 조용히 앞 3개만 남기는데,
    # 이건 "LLM이 실수로 4개를 뽑았다"는 모델 품질 문제지 사용자가 검증을 우회하려는
    # 상황(regions)이 아니라서 요청 자체를 실패시킬 이유가 없기 때문이다.
    # verifiable=false 태그는 검색 호출을 안 만드니(naver_local_search.py) 이
    # 상한과 무관하게 그대로 둔다.
    @field_validator("liked_tags", "disliked_tags")
    @classmethod
    def cap_verifiable_tags(cls, v: list[PreferenceTag]) -> list[PreferenceTag]:
        verifiable = [t for t in v if t.verifiable][:MAX_VERIFIABLE_TAGS]
        non_verifiable = [t for t in v if not t.verifiable]
        return verifiable + non_verifiable


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
    # place_candidates에서 결정론적으로 부착(lat/lng와 같은 방식) — 이 장소가
    # naver_local_search의 verifiable liked_tags 태그 검색("{region} {tag}")에서
    # 나온 것이면 그 태그 문자열, 아니면 None(카테고리 검색에서만 나왔거나 환각
    # 장소). Step3._rule_based_filter가 "같은 태그를 만족한 활동이 한 후보에
    # 2곳 이상이면 하드 위반"을 판단하는 데 쓴다(2026-08-11 설계) — LLM이
    # category/title 텍스트로 사후 추측하던 걸 검색 단계에서 이미 확정된 값으로
    # 대체.
    matched_tag: str | None = None
    # place_candidates에서 결정론적으로 부착(matched_tag와 같은 방식) — 이 장소가
    # naver_local_search의 카테고리 검색(맛집/카페/액티비티/문화시설) 중 어느
    # 쿼리에서 나왔는지. 네이버 원본 category 문자열은 카페도 "음식점>카페,디저트"
    # 로 묶여있어(실측 확인) "식사 가능한 곳"과 "디저트만 되는 곳"을 못 가르는데,
    # 우리가 무슨 쿼리로 찾았는지는 확실한 근거다. Step3가 "점심/저녁 시간대에
    # 맛집 카테고리 활동이 있는지"를 판단하는 데 쓴다(2026-08-11 설계).
    source_category: str | None = None


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
# `Candidate.routes`는 그래서 빈 리스트가 기본값이다. synthesize_and_validate()가
# CandidateDraft/ActivityDraft를 여기 Activity로 변환한다(order 부여, operating_hours
# 는 항상 빈 문자열+info_needs_check=True, map_url은 naver_map_url.build_naver_map_url()
# 로 생성 — 영업시간 자동 확인을 포기하는 대신 사용자가 클릭 한 번으로 확인하게 유도).


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
    # naver_map_url.build_naver_map_url()로 만든 링크 — 영업시간을 자동 확인 못 하는
    # 대신(info_needs_check=True) 사용자가 클릭 한 번으로 직접 확인하게 유도.
    map_url: str = ""
    # ActivityDraft에서 그대로 복사(2026-08-10) — Step4(enrich_routes)가 구간별
    # 이동 옵션을 조회하려면 좌표가 필요한데, 사용자가 실제로 고르는 건 이
    # Activity(Candidate.activities)이지 ActivityDraft가 아니다. 여기서 빠지면
    # Step4가 좌표를 못 구해 라우터에서 다시 장소를 찾아야 하는 낭비가 생긴다.
    lat: float | None = None
    lng: float | None = None


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
    # POST /schedules와 GET /schedules/{id}가 함께 돌려주는 검색 스냅샷. 최종
    # 후보와 달리 "일정을 만들기 위해 무엇을 검색했는지"를 보여주는 보조 정보다.
    # 파이프라인 순수 함수 단독 호출에서는 만들지 않으므로 기본값은 None이다.
    place_pool: dict | None = None
    # 확정된 뒤 생긴 공유 링크가 있으면 같이 돌려준다 — GET /schedules/{id}가
    # 새로고침 후에도 공유 slug를 복구할 수 있게 한다(2026-08-10, Finding 1).
    share_slug: str | None = None


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
    # 지도에 그릴 실제 경로 좌표(lat, lng 순서). 없으면 빈 리스트 — 호출부(프런트)가
    # 두 지점을 직선으로 잇는 폴백을 그린다. 도보는 API 호출이 없어(직선거리
    # 추정만) 항상 빈 리스트.
    path: list[tuple[float, float]] = []


class RouteSegment(BaseModel):
    from_order: int
    to_order: int
    options: list[RouteOption]
    recommended_option_id: str
    selected_option_id: str

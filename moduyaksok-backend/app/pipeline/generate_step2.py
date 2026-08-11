# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 2 — 후보 생성 Fan-out (MoA Proposer). 관점이 다른 프롬프트
#              N=3개를 병렬 호출해 서로 다른 CandidateDraft를 만든다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, PreferenceTag.verifiable 처리 방침 명시 — "사람 많은 곳"처럼 확인할
#             데이터가 없는 주관적 태그를 어떻게 다룰지 설계
# 2026-08-09, 실제 구현. call_structured가 동기 함수라 스레드풀로 감싸서
#             병렬화. 개별 관점 timeout 180초(실측 전이라 널널하게),
#             return_exceptions=True로 부분 실패 허용. 프롬프트는 RTF만 쓰고
#             few-shot은 생략 — 생성 작업에 few-shot을 넣으면 3개 관점이 예시
#             스타일로 수렴해 "실질적 차별성 확보"라는 이 Step의 목표를 해칠 수
#             있다고 판단.
# 2026-08-09, asyncio.wait_for(내부적으로 asyncio.timeout() 사용)가 DeepEval
#             eval 테스트 안에서 "RuntimeError: Timeout should be used inside a
#             task"로 3개 호출이 통째로 실패하는 문제를 실측으로 확인 — 원인은
#             DeepEval의 GEval.measure()가 내부적으로 거는 nest_asyncio 패치가
#             전역 상태라, 같은 프로세스 안에서 그 패치가 걸린 *이후*에 생성되는
#             모든 새 이벤트루프/태스크의 asyncio.timeout() current-task 감지가
#             깨짐(스크립트 단독 실행·같은 세션의 첫 eval 테스트는 정상, 두 번째
#             테스트부터 재현). asyncio.wait_for/asyncio.timeout을 아예 안 쓰는
#             구조로 변경 — concurrent.futures.Future.result(timeout=...)로
#             스레드 안에서 타임아웃을 처리하고, async 경계는
#             loop.run_in_executor 한 번만 넘는다.
# 2026-08-09, tests/eval/golden_step2.py의 budget_conscious_selection 케이스가
#             GEval 0.50/0.7로 실패 — place_candidates에 가격 정보가 없어서
#             모델이 예산 대비 카테고리 위험도를 스스로 추론해야 하는데,
#             프롬프트가 budget_per_person을 "지켜라"고만 하고 판단 기준을
#             안 줘서 파인다이닝 카테고리를 예산 무시하고 넣는 걸 실측으로 확인.
#             "카테고리 이름이 명백히 고가면 제외해라"를 Task에 명시해서 재실측
#             — 골든 4케이스 재통과(0.70~0.90).
# 2026-08-09, 골든 데이터의 place_candidates가 3~4개뿐이라 관점 3개가 결국 같은
#             장소들을 돌려써서 초안이 서로 비슷해지는 문제 확인 — 데이터 늘리는
#             것과 별개로, PERSPECTIVES 자체가 "이 관점을 최우선으로 고려해라: "
#             + 한 줄 라벨뿐이라 관점별로 뭘 다르게 해야 하는지가 모호했던 것도
#             원인. PERSPECTIVES를 (라벨, 상세 지시문) 쌍으로 바꿔서 관점마다
#             구체적 판단 기준(실내/실외 구분, 동선은 address 근접도로 판단, 취향
#             태그 최대 반영 기준)을 따로 명시.
# 2026-08-09, NormalizedConditions.region: str -> regions: list[str] 변경(Task 1)에
#             맞춰 _build_user_prompt가 지역을 콤마로 이어 붙여 전부 프롬프트에
#             주입하도록 수정.
# 2026-08-09, eval 재실행에서 재현된 미해결 이슈 3건 중 2건 해결:
#             (1) Solar가 activity의 name/category를 다른 place_candidates 항목
#             것과 뒤섞어 반환하는 결함 — 프롬프트로 못 고치는 모델 신뢰성 문제라,
#             반환 직전 _correct_categories()로 place_candidates 기준 category를
#             결정론적으로 재보정(LLM이 만든 category는 아예 안 믿음).
#             (2) 활동 가격 합이 budget_per_person을 넘는데도 "초과될 수 있다"고만
#             적고 그대로 내는 사례 실측 — Task에 "하한 합 계산해서 넘으면 다시
#             구성해라" 명시.
#             (3) place_candidates가 적을 때 같은 장소를 반복 방문시켜 time_range를
#             억지로 채우는 사례도 실측 — "같은 장소는 최대 1번만, 활동 개수 줄여도
#             된다"고 명시.
# 2026-08-09, MID -> HIGH 티어로도 예산 합산/반복방지/시간 겹침 없음을 한 번에
#             다 못 지키는 사례가 남아있는 걸 실측 확인 — 한 LLM 호출에 너무 많은
#             제약(환각 방지·verifiable 하드/소프트·예산·반복방지·시간 겹침 없음·
#             관점 반영)을 동시에 시키는 게 근본 원인이라고 판단. "장소 선택"(LLM,
#             CandidateSelectionDraft)과 "시간 배정"(결정론적 계산, _schedule_places)
#             을 분리 — 시간 겹침 없음은 이제 계산 구조상 항상 보장되고, LLM은
#             장소 선택·예산·취향 판단에만 집중한다. 골든 5케이스 재실측 결과
#             5/5 통과(전부 0.80) — 분리 전엔 프롬프트/기준을 여러 번 고쳐도
#             매번 2~3개가 실패했는데, 분리 직후 한 번에 전부 통과함. judge
#             reason에서도 시간 겹침·time_range 위반 지적이 5케이스 전부 사라짐 —
#             "LLM에게 한 번에 너무 많이 시키지 말고, 결정론적으로 계산 가능한
#             부분은 코드로 떼어내라"는 게 이 프로젝트의 유효한 처방으로 확인됨.
# 2026-08-10, _schedule_places()의 활동 사이 버퍼를 고정 30분에서 place_candidates
#             좌표 기반 추정(travel_estimate.estimate_buffer_minutes)으로 변경 —
#             이동 동선 보강을 사용자가 고른 후보 1개에만 돌리기로 파이프라인
#             순서를 바꾸면서(Step1→2→3→사용자 선택→4, docs/AI파이프라인_Step별_
#             설계 "전체 흐름" 참고), Step2 시점에 아예 이동시간을 모르는 채로
#             시간을 배정하던 문제가 더 커져서 개선. 좌표를 못 찾으면 기존
#             고정값으로 폴백해 기존 유닛 테스트는 그대로 통과한다. ActivityDraft
#             에도 address/lat/lng을 결정론적으로 부착 — Step4의 ODsay 호출과
#             reconcile_schedule() 재조정이 이 값을 쓴다.
# 2026-08-10, generate_candidates_with_perspectives()/generate_single_candidate()
#             추가 — Step3가 하드 위반으로 후보를 드롭했을 때 "그 후보를 만든
#             관점만" 다시 생성하는 재시도(app/pipeline/orchestrate.py)를 위해
#             필요. 기존 generate_candidates()는 어떤 CandidateDraft가 어느
#             관점에서 나왔는지 버리고 있었음 — _call_all_perspectives_sync의
#             future_to_perspective 제출 순서가 PERSPECTIVES 순서와 같다는 점을
#             이용해 라벨을 붙였다. generate_candidates()는 이 새 함수의 얇은
#             래퍼로 바꿔서 기존 시그니처·테스트는 그대로 유지.
# 2026-08-11, 두 가지 추가:
#             (1) place_candidates에 naver_local_search가 붙여준 matched_tag를
#             ActivityDraft까지 그대로 옮긴다(_matched_tag_by_title, lat/lng와 같은
#             패턴) — Step3가 "같은 verifiable 태그를 만족하는 활동이 한 후보에
#             2곳 이상"을 판단하는 근거. _ROLE_TASK에도 "같은 태그는 후보당 최대
#             1곳이면 충분하다"를 명시해 애초에 덜 만들도록 지시(2026-08-10 미해결
#             설계 질문의 (a) 해소) — 그래도 지켜지지 않을 경우를 Step3가 하드
#             룰로 한 번 더 잡는다.
#             (2) purpose(date/friends/family/party/other)가 지금까지 프롬프트에
#             "목적: date"처럼 원문 그대로만 들어가고 어떻게 반영하라는 지시가
#             없었다(사용자가 지적, 실측해보니 이 프로젝트의 다른 조건들과 달리
#             purpose만 유일하게 전용 지시문이 없었음) — _PURPOSE_GUIDANCE로
#             목적별 구체 지시문을 추가.
# 2026-08-11, 사용자 관측 2건 대응 — (1) 관점 3개가 비슷한 후보를 만듦(같은
#             취향 태그 매칭 장소를 관점들이 동시에 욕심냄), (2) 식사(점심/저녁)
#             없이 디저트/카페만으로 채워지는 경우가 있음(강한 liked_tag가 있을 때).
#             둘 다 "LLM 지시만으로는 못 믿는다"는 이 프로젝트 기존 결론에 따라
#             결정론적으로 해소:
#             (1) _tag_bundles_by_perspective() — 관점마다 다른 태그 매칭 장소를
#             "시드"로 배정하고, 다른 태그는 그 시드와 좌표상 가장 가까운 매칭으로
#             채운 뒤, 관점별로 서로 다른 place_candidates 부분집합을 준다(전부
#             똑같은 풀을 보여주던 것에서 변경) — 같은 곳을 여러 관점이 동시에
#             볼 수조차 없게 만들어 겹침을 원천 차단. 좌표는 mapx/mapy를 그대로
#             쓴다(Step4 이동시간 추정과 같은 값, travel_estimate.haversine_
#             distance_m 재사용 — 새 지역 문자열 필드를 따로 안 만듦).
#             (2) 카테고리 검색(맛집/카페/액티비티/문화시설) 소싱 시점에 어느
#             버킷에서 나왔는지를 place dict에 source_category로 부착(naver_
#             local_search.py, matched_tag와 같은 패턴)하고 ActivityDraft까지
#             그대로 옮김. time_range가 점심(12~13시)/저녁(18~19시) 시간대를
#             포함하면 그 시간대에 [맛집] 장소를 최소 1곳 포함하라고 유저
#             프롬프트에 동적으로 지시(1차, _meal_slot_instruction) — Step3에
#             하드룰 백스탑을 추가(2차, synthesize_step3.py 참고). 무조건 정확히
#             그 시각에 먹으라는 게 아니라 "그 시간대가 일정에 껴 있으면 식사
#             하나는 넣는다"는 느슨한 기준(사용자 제안).
#             place_candidates 표시 텍스트에도 [맛집] 같은 버킷 라벨을 붙여서
#             (_format_place_candidates) LLM이 텍스트로 카테고리를 추측하지
#             않고 바로 참조하게 함.
# 2026-08-11(2차), NormalizedConditions.regions: list[str] -> region: str로 축소되면서
#             _build_user_prompt의 지역 표시를 단일 값으로 변경. naver_local_search의
#             카테고리가 4개("맛집" 등)에서 15개로 세분화되며 "맛집" 하나로 뭉뚱그려
#             참조하던 _meal_slot_instruction/_MEAL_CATEGORIES도 세분화된 식사류
#             카테고리 집합을 참조하게 변경(synthesize_step3.py와 같은 목록을
#             독립적으로 유지, naver_local_search.py도 동일).
# ------------------------------------------------------------------
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import (
    ActivityDraft,
    CandidateDraft,
    CandidateSelectionDraft,
    NormalizedConditions,
    PlaceSelectionDraft,
    PreferenceTag,
)
from app.pipeline.travel_estimate import estimate_buffer_minutes, haversine_distance_m
from app.services.structured_llm import call_structured

# MID -> HIGH로 격상(2026-08-09, 장소선택/시간배정 분리 이전). 예산 합산·중복
# 방문 금지 지시를 추가하자 MID(solar-pro)가 하드 제약들을 동시에 못 버티는 걸
# 실측 확인. 분리 이후에도 LLM이 여전히 예산·취향 등 여러 판단을 하므로 HIGH 유지.
TIER = ModelTier.HIGH

# 관점을 다르게 줘서 후보 간 실질적 차별성을 확보한다 (기술설계 §4 Step 2).
# (라벨, 상세 지시문) 쌍 — 라벨만 주면 관점별로 뭘 다르게 판단해야 하는지 모델이
# 알아서 해석하게 되고, 그러면 place_candidates가 적을 때 세 관점이 결국 비슷한
# 선택으로 수렴한다(실측 확인, 2026-08-09). 관점마다 구체적 판단 기준을 명시.
PERSPECTIVES: tuple[tuple[str, str], ...] = (
    (
        "실내 중심, 가성비 우선",
        "category로 실내 장소임을 판단할 수 있는 곳(카페, 음식점, 실내 체험/전시/"
        "보드게임카페 등)을 우선 선택하고, 공원·산책로·야외 피크닉존처럼 명백히 "
        "실외인 장소는 피해라. price_range_per_person의 하한이 낮은 장소를 우선 "
        "배치해 budget_per_person 대비 여유를 최대한 남겨라.",
    ),
    (
        "동선 최소화 우선",
        "place_candidates의 address/roadAddress를 비교해서 서로 가장 가까운(같은 "
        "동·인접 구역) 장소들로만 구성해라. 다른 동·지역에 있는 장소를 섞지 말고, "
        "필요하면 활동 개수를 줄여서라도 이동 거리를 줄여라.",
    ),
    (
        "사용자 취향 태그 최대 반영",
        "liked_tags 중 verifiable=true인 태그와 category/title이 일치하는 장소를 "
        "최대한 많이 포함해라(가능하면 하나도 빠짐없이). verifiable=false인 "
        "liked_tags도 장소 유형(관광명소/한적한 동네 가게 등)으로 미루어 최대한 "
        "반영하되 절대 보장한다고 말하지 마라.",
    ),
)

# purpose별 지시문 — 지금까지 프롬프트에 "목적: date"처럼 원문만 들어가고
# 어떻게 반영하라는 지시가 없어서 LLM의 일반 상식에만 의존하고 있었다(2026-08-11
# 확인, 검증된 적 없는 신호였음). budget/tags처럼 구체 기준을 준다. "other"는
# 목적이 특정되지 않은 경우라 별도 지시 없이 무난하게 구성하도록 빈 문자열로
# 둔다.
_PURPOSE_GUIDANCE: dict[str, str] = {
    "date": (
        "데이트 목적이다 — 2인이 나란히 즐기기 좋은 분위기 있는 장소(카페, 전시, "
        "야경, 체험 등) 위주로 구성해라. 시끄럽고 번잡한 곳보다 대화하거나 함께 "
        "경험하기 좋은 곳을 우선해라."
    ),
    "friends": (
        "친구 모임 목적이다 — 여러 명이 편하게 어울리며 대화·활동하기 좋은 곳"
        "(맛집, 카페, 액티비티) 위주로 구성해라. 격식 있는 곳보다 캐주얼한 곳을 "
        "우선해라."
    ),
    "family": (
        "가족 모임 목적이다 — 다양한 연령대가 무리 없이 이동·이용할 수 있는 곳 "
        "위주로 구성해라. 계단이 많거나 오래 서서 기다려야 하는 곳, 소음이 심한 "
        "곳은 피해라."
    ),
    "party": (
        "파티/단체 모임 목적이다 — 여러 명이 왁자지껄하게 즐길 수 있는 곳(대형 "
        "식당, 펍, 액티비티 등) 위주로 구성해라. 조용하고 차분한 분위기의 장소는 "
        "피해라."
    ),
    "other": "",
}

# 개별 관점 호출 타임아웃(초). 각 호출이 실제로 얼마나 걸릴지 아직 실측 전이라
# 널널하게 잡음 — 실측 후 필요하면 좁힐 것 (기술설계 §4 "파이프라인 오류/타임아웃
# 처리"의 "예: 20초"는 참고 예시일 뿐, 이 프로젝트는 3분으로 결정).
TIMEOUT_SECONDS = 180

# _schedule_places()가 쓰는 시간 배정 상수. 활동 하나당 30~90분 사이로 잡는다.
# 활동 사이 이동 버퍼는 2026-08-10부터 place_candidates의 좌표로 구간마다
# estimate_buffer_minutes()를 불러 다르게 잡는다(travel_estimate.py) — 좌표를
# 못 찾을 때(환각 장소 등)만 이 고정값으로 폴백한다. Step4(사용자가 후보를 고른
# 뒤에만 그 후보에 한해 실행 — docs/AI파이프라인_Step별_설계 Step4 절 참고)가
# 실제 ODsay 이동시간을 알아내면 travel_estimate.reconcile_schedule()로 이 추정을
# 실제값으로 교정한다.
_ACTIVITY_BUFFER_MINUTES = 30
_MIN_ACTIVITY_MINUTES = 30
_MAX_ACTIVITY_MINUTES = 90

# LLM에게 넘길 한 관점의 장소 후보는 이 반경 안의 장소로 제한한다. 기존에는
# 좌표를 시간 버퍼 계산과 60분 초과 사후 탈락에만 써서, 카테고리 전체 후보를
# LLM이 함께 보고 먼 장소를 섞을 수 있었다. 중심에서 2.5km면 양 끝 장소도
# 대체로 5km 이내라, Step3의 30분 이동 하드룰과도 자연스럽게 맞는다.
_COMPACT_POOL_RADIUS_METERS = 2_500

# 식사 슬롯 판단 기준(2026-08-11) — synthesize_step3.py에도 같은 상수·로직이
# 독립적으로 있다(이 프로젝트 관례상 파이프라인 단계끼리는 서로 안 부르고, 작은
# 헬퍼는 각자 파일에 둔다 — _format_tags()도 이미 두 파일에 각각 있음).
_LUNCH_WINDOW = (time(12, 0), time(13, 0))
_DINNER_WINDOW = (time(18, 0), time(19, 0))
# naver_local_search._PLACE_CATEGORIES 중 "식사가 되는" 카테고리 — 그쪽과 같은
# 목록을 독립적으로 유지한다(위 주석과 같은 이유). 카테고리 목록을 바꿀 땐
# 두 파일(naver_local_search.py, synthesize_step3.py) 다 같이 확인할 것.
_MEAL_CATEGORIES = frozenset({"한식", "중식", "일식", "양식", "분식", "고깃집"})

_ROLE_TASK = """\
# Role
너는 주어진 조건과 장소 후보 목록 안에서 만남 일정에 쓸 장소를 고르는 전문 플래너다.

# Task
- place_candidates 목록에 있는 장소만 골라라. 목록에 없는 장소를 지어내지 마라.
- 같은 장소를 두 번 이상 고르지 마라 — 각 장소는 이 초안에서 최대 1번만 쓴다.
- headcount(인원 수), budget_per_person(1인 예산) 조건을 고려해라. place_candidates에는 \
가격 정보가 없으니 category/title 이름만으로 판단해라 — '파인다이닝', '오마카세'처럼 \
카테고리 이름 자체가 명백히 고가를 뜻하는 장소는 budget_per_person이 낮으면(예: 2만원 \
이하) 고르지 마라.
- 고른 장소들의 price_range_per_person 하한을 모두 더해봐라. 그 합이 budget_per_person을 \
넘으면 장소를 빼거나 더 저렴한 후보로 바꿔서 합이 budget_per_person 이내가 되게 다시 \
골라라.
- disliked_tags 중 verifiable=true인 태그는 place_candidates의 category/title로 판단해 \
반드시 배제해라.
- liked_tags 중 verifiable=true인 태그는 place_candidates의 category/title로 판단해 \
최대한 반영해라. 단, 같은 태그를 만족하는 장소는 이 후보(코스)당 최대 1곳이면 \
충분하다 — 이미 그 태그를 만족하는 장소를 하나 골랐으면, 같은 태그를 또 만족하는 \
곳을 추가하지 말고 다른 태그나 다른 카테고리로 채워라.
- verifiable=false인 태그(liked/disliked 모두)는 확인할 방법이 없는 주관적 취향이다 — \
참고만 하고 절대 보장한다고 말하지 마라. rationale에서도 "사람이 없습니다"처럼 단정하지 \
말고 "비교적 한산한 편인 곳으로 골랐어요"처럼 hedge된 표현을 써라.
- time_range(시작~종료 시각) 안에서 자연스럽게 소화할 수 있을 만큼만 장소를 골라라 \
(보통 2~5곳). 정확한 시작·종료 시각이나 장소 사이 이동시간은 신경 쓰지 마라 — places \
목록을 방문할 순서대로만 나열하면, 시간 배정은 이 단계 이후에 별도로 계산된다.
- 이번 초안은 다음 관점을 최우선으로 고려해라: {label}. 구체적으로: {instruction}

# Format
title(일정 제목), places(각 항목은 name/category/price_range_per_person(1인당 최소~최대 \
가격) — 방문 순서대로 나열), rationale(이 초안을 왜 이렇게 짰는지, {label} 관점을 \
어떻게 반영했는지 설명)\
"""


def _format_tags(tags: list[PreferenceTag]) -> str:
    if not tags:
        return "(없음)"
    return ", ".join(f"{t.tag}(verifiable={t.verifiable})" for t in tags)


def _format_place_candidates(place_candidates: list[dict]) -> str:
    if not place_candidates:
        return "(없음 — 이 조건으로는 활동을 채울 장소가 없다는 뜻이니 최소한의 \
초안만 만들어라)"
    lines = []
    for p in place_candidates:
        bucket = p.get("source_category")
        bucket_label = f" [{bucket}]" if bucket else ""
        lines.append(
            f"- {p.get('title', '')} | {p.get('category', '')}{bucket_label} | "
            f"{p.get('roadAddress') or p.get('address', '')}"
        )
    return "\n".join(lines)


def _required_meal_windows(time_range: tuple[datetime, datetime]) -> list[tuple[time, time]]:
    """time_range가 점심(12~13시)/저녁(18~19시) 구간을 포함하면 그 구간을 필수
    식사 슬롯으로 반환한다 — 무조건 그 시각에 먹으라는 게 아니라, 그 시간대가
    일정에 껴 있으면 식사 하나는 넣는 게 자연스럽다는 느슨한 기준(2026-08-11,
    사용자 제안). 나중에 피드백 단계(POST /schedules/{id}/feedback, 아직
    미구현)에서 "점심은 만나서 먹을 거예요" 같은 입력이 이 요구사항 자체를
    덮어쓰게 하면 된다.
    """
    start, end = time_range
    windows: list[tuple[time, time]] = []
    if start.time() <= _LUNCH_WINDOW[0] and end.time() >= _LUNCH_WINDOW[1]:
        windows.append(_LUNCH_WINDOW)
    if start.time() <= _DINNER_WINDOW[0] and end.time() >= _DINNER_WINDOW[1]:
        windows.append(_DINNER_WINDOW)
    return windows


def _meal_slot_instruction(time_range: tuple[datetime, datetime]) -> str:
    windows = _required_meal_windows(time_range)
    if not windows:
        return ""
    labels = {_LUNCH_WINDOW: "점심(12:00~13:00 부근)", _DINNER_WINDOW: "저녁(18:00~19:00 부근)"}
    parts = [labels[w] for w in windows]
    meal_labels = "/".join(f"[{c}]" for c in sorted(_MEAL_CATEGORIES))
    return (
        f"이 시간대엔 {', '.join(parts)}이(가) 껴 있다 — 해당 시간대에 식사가 되는 "
        f"카테고리({meal_labels} 중 하나) 표시된 장소를 최소 1곳씩 포함해라(정확히 "
        "그 시각일 필요는 없고 자연스러운 범위면 된다). 식사 장소는 방문 순서에도 "
        "점심부터 저녁 순으로 넣어라. 시간 배정기는 이 순서를 바탕으로 실제 식사 "
        "시각에 배치한다. 나머지 시간은 자유롭게(카페/액티비티/문화시설 등으로) 채워라."
    )


def _build_system_prompt(perspective: tuple[str, str]) -> str:
    label, instruction = perspective
    return _ROLE_TASK.format(label=label, instruction=instruction)


def _format_purpose(purpose: str) -> str:
    guidance = _PURPOSE_GUIDANCE.get(purpose, "")
    return f"{purpose} ({guidance})" if guidance else purpose


def _build_user_prompt(conditions: NormalizedConditions, place_candidates: list[dict]) -> str:
    start, end = conditions.time_range
    meal_instruction = _meal_slot_instruction(conditions.time_range)
    return (
        f"목적: {_format_purpose(conditions.purpose)}\n"
        f"인원: {conditions.headcount}명\n"
        f"시간: {start.isoformat()} ~ {end.isoformat()}\n"
        + (f"{meal_instruction}\n" if meal_instruction else "")
        + f"지역(place_candidates는 이 지역에서 조회된 것): {conditions.region}\n"
        f"1인 예산: {conditions.budget_per_person}원\n"
        f"좋아하는 것: {_format_tags(conditions.liked_tags)}\n"
        f"싫어하는 것: {_format_tags(conditions.disliked_tags)}\n\n"
        f"장소 후보 목록(place_candidates):\n{_format_place_candidates(place_candidates)}"
    )


def _tag_bundles_by_perspective(
    place_candidates: list[dict], num_perspectives: int
) -> list[list[dict]]:
    """관점마다 사용할 좌표 기반 근거리 후보 묶음을 결정론적으로 만든다.

    이전 구현은 liked 태그 장소만 좌표로 묶고, 카테고리 검색 장소는 모두 공유했다.
    따라서 LLM이 카테고리 장소를 서로 멀리 섞어도 60분을 넘기기 전까지는 통과할
    수 있었다. 이제 모든 후보를 반경 2.5km의 지역 묶음으로 먼저 자른다.

    묶음 점수는 식사 가능한 카테고리, 카테고리 다양성, 좋아요 태그, 후보 수를
    함께 보므로 단순히 장소가 많은 상권보다 실제 일정으로 구성 가능한 중심을
    우선한다. 서로 다른 중심을 우선 선택해 관점 차이도 유지하지만, 충분한 다른
    중심이 없으면 가장 좋은 묶음을 재사용한다.
    """

    def coords(place: dict) -> tuple[float, float] | None:
        mapx, mapy = place.get("mapx"), place.get("mapy")
        if mapx is None or mapy is None:
            return None
        try:
            return float(mapy) / 1e7, float(mapx) / 1e7
        except (TypeError, ValueError):
            return None

    located = [(place, point) for place in place_candidates if (point := coords(place)) is not None]
    # 좌표가 아예 없는 응답은 기존 동작으로 폴백한다. 실제 선택된 장소는 Step3가
    # 좌표 누락을 환각으로 드롭하므로, 이 경우도 조용한 품질 저하가 아니라 재생성
    # 또는 명확한 생성 불가로 끝난다.
    if not located:
        return [list(place_candidates) for _ in range(num_perspectives)]

    neighborhoods: list[
        tuple[dict, tuple[float, float], list[dict], tuple[int, int, int, int]]
    ] = []
    for seed, seed_coord in located:
        nearby = [
            place
            for place, point in located
            if haversine_distance_m(seed_coord[0], seed_coord[1], point[0], point[1])
            <= _COMPACT_POOL_RADIUS_METERS
        ]
        meal_count = sum(p.get("source_category") in _MEAL_CATEGORIES for p in nearby)
        category_count = len({p.get("source_category") for p in nearby if p.get("source_category")})
        matched_tag_count = sum(bool(p.get("matched_tag")) for p in nearby)
        # 이름을 마지막 tie-breaker로 써서 네트워크 응답 순서가 달라져도 결과가 흔들리지 않는다.
        score = (meal_count, category_count, matched_tag_count, len(nearby))
        neighborhoods.append((seed, seed_coord, nearby, score))

    neighborhoods.sort(key=lambda item: (item[3], item[0].get("title", "")), reverse=True)
    selected: list[tuple[dict, tuple[float, float], list[dict], tuple[int, int, int, int]]] = []
    for neighborhood in neighborhoods:
        _, center, _, _ = neighborhood
        if all(
            haversine_distance_m(center[0], center[1], existing[1][0], existing[1][1])
            > _COMPACT_POOL_RADIUS_METERS
            for existing in selected
        ):
            selected.append(neighborhood)
        if len(selected) == num_perspectives:
            break

    if not selected:
        return [list(place_candidates) for _ in range(num_perspectives)]
    return [list(selected[i % len(selected)][2]) for i in range(num_perspectives)]


def _call_all_perspectives_sync(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[CandidateSelectionDraft | BaseException]:
    """스레드 하나 안에서 관점 3개를 병렬 제출하고, 각각 개별 timeout으로
    result()를 기다린다. asyncio.wait_for/asyncio.timeout을 쓰지 않아 이걸
    호출하는 async 쪽이 어떤 이벤트루프/nest_asyncio 상태에 있든 영향받지 않는다.
    관점마다 _tag_bundles_by_perspective()가 만든 서로 다른 place_candidates
    부분집합을 넘긴다(2026-08-11) — 예전엔 3개 관점 모두 동일한 place_candidates를
    봤다.
    """
    per_perspective_candidates = _tag_bundles_by_perspective(place_candidates, len(PERSPECTIVES))
    with ThreadPoolExecutor(max_workers=len(PERSPECTIVES)) as executor:
        future_to_perspective = {
            executor.submit(
                call_structured,
                provider=provider,
                api_key=api_key,
                model=get_model(provider, TIER),
                system=_build_system_prompt(perspective),
                user=_build_user_prompt(conditions, per_perspective_candidates[i]),
                schema=CandidateSelectionDraft,
            ): perspective
            for i, perspective in enumerate(PERSPECTIVES)
        }
        results: list[CandidateSelectionDraft | BaseException] = []
        for future in future_to_perspective:
            try:
                results.append(future.result(timeout=TIMEOUT_SECONDS))
            except Exception as exc:
                results.append(exc)
        return results


def _correct_categories(
    selection: CandidateSelectionDraft, place_candidates: list[dict]
) -> CandidateSelectionDraft:
    """LLM이 돌려준 place.category는 못 믿는다 — Solar가 서로 다른 두 장소의
    name/category를 뒤섞어 반환하는 결함이 실측으로 확인됨(2026-08-09, golden_step2.py
    soft_signal_crowdedness_needs_hedge 등에서 재현). name이 place_candidates의
    title과 정확히 일치하면 category를 그 place_candidates 항목 것으로 덮어쓴다 —
    place_candidates는 이미 확정된 신뢰 데이터라 LLM이 다시 만들 필요가 없다.
    일치하는 title이 없으면(환각 의심) 손대지 않는다 — 그건 GEval 채점의 몫이다.
    """
    category_by_title = {p.get("title", ""): p.get("category", "") for p in place_candidates}
    corrected_places = [
        place.model_copy(update={"category": category_by_title[place.name]})
        if place.name in category_by_title
        else place
        for place in selection.places
    ]
    return selection.model_copy(update={"places": corrected_places})


def _coords_by_title(place_candidates: list[dict]) -> dict[str, tuple[float, float, str]]:
    """title -> (lat, lng, address). mapx/mapy가 없거나 파싱 안 되는 항목은 건너뛴다
    — 이 경우 해당 장소는 좌표 기반 버퍼 추정 대상에서 빠지고 고정 버퍼로 폴백된다.
    """
    coords: dict[str, tuple[float, float, str]] = {}
    for p in place_candidates:
        title = p.get("title", "")
        mapx, mapy = p.get("mapx"), p.get("mapy")
        if not title or mapx is None or mapy is None:
            continue
        try:
            lat, lng = float(mapy) / 1e7, float(mapx) / 1e7
        except (TypeError, ValueError):
            continue
        coords[title] = (lat, lng, p.get("roadAddress") or p.get("address", ""))
    return coords


def _matched_tag_by_title(place_candidates: list[dict]) -> dict[str, str]:
    """title -> matched_tag. naver_local_search.search_places_for_region()가
    liked_tags 태그 검색("{region} {tag}")에서 나온 장소에만 결정론적으로 붙여준
    값을 그대로 옮긴다(2026-08-11) — 카테고리 검색에서만 나온 장소나 환각 장소는
    이 dict에 없다.
    """
    return {
        p["title"]: p["matched_tag"]
        for p in place_candidates
        if p.get("title") and p.get("matched_tag")
    }


def _source_category_by_title(place_candidates: list[dict]) -> dict[str, str]:
    """title -> source_category(맛집/카페/액티비티/문화시설). naver_local_search가
    카테고리 검색 버킷에서 결정론적으로 붙여준 값을 그대로 옮긴다(2026-08-11,
    matched_tag와 같은 패턴) — Step3가 점심/저녁 슬롯에 실제 식사류가 있는지
    판단하는 근거로 쓴다.
    """
    return {
        p["title"]: p["source_category"]
        for p in place_candidates
        if p.get("title") and p.get("source_category")
    }


def _meal_anchor_starts(
    places: list[PlaceSelectionDraft],
    time_range: tuple[datetime, datetime],
    source_categories: dict[str, str],
) -> dict[int, datetime]:
    """점심·저녁 식사 장소를 실제 식사 시간대에 배치할 앵커를 만든다.

    이전에는 Step3가 12-13시와 18-19시의 식사를 하드 검증하면서도,
    _schedule_places()는 모든 활동을 시작 시각부터 빈틈없이 앞당겨 배치했다.
    특히 10-21시처럼 긴 기본 입력에서는 저녁까지 도달하지 못해 후보 풀이
    충분해도 전부 드롭될 수 있었다. 선택된 식사 장소의 방문 순서를 보존하면서
    첫 식사는 첫 필수 창, 마지막 식사는 마지막 필수 창에 맞춰 공백을 배정한다.

    식사 장소 개수가 필요한 창보다 적으면 빈 dict를 반환한다. 이 경우에는
    Step3가 기존 하드룰로 후보를 재생성하게 하므로, 식사 없이 통과시키지 않는다.
    """
    windows = _required_meal_windows(time_range)
    if not windows:
        return {}
    meal_indices = [
        i for i, place in enumerate(places) if source_categories.get(place.name) in _MEAL_CATEGORIES
    ]
    if len(meal_indices) < len(windows):
        return {}

    if len(windows) == 1:
        selected_indices = [meal_indices[0]]
    else:
        # 첫·마지막 식사 장소를 각각 이른·늦은 식사 창에 붙이면 LLM이 고른
        # 방문 순서도 유지하고, 중간 활동은 두 끼 사이로 자연스럽게 들어간다.
        selected_indices = [meal_indices[0], meal_indices[-1]]

    date = time_range[0].date()
    return {
        index: datetime.combine(date, window[0])
        for index, window in zip(selected_indices, windows, strict=True)
    }


def _schedule_places(
    places: list[PlaceSelectionDraft],
    time_range: tuple[datetime, datetime],
    place_candidates: list[dict] | None = None,
) -> list[ActivityDraft]:
    """LLM이 고른 장소 목록(방문 순서대로)에 시간을 배정한다 — 결정론적 계산이라
    LLM에게 시키지 않는다(2026-08-09 결정, 이 파일 변경 이력 참고). 활동 하나당
    지속시간을 _MIN_ACTIVITY_MINUTES~_MAX_ACTIVITY_MINUTES 사이로 window 크기에
    맞춰 정하고, 활동 사이 버퍼는 place_candidates 좌표가 있으면
    estimate_buffer_minutes()로 구간마다 다르게, 없으면(place_candidates 생략 —
    유닛 테스트 기본값, 또는 좌표를 못 찾은 환각 장소) _ACTIVITY_BUFFER_MINUTES로
    고정 배정한다. 순서대로 이어붙이므로 활동끼리 겹치는 일이 계산 구조상 생기지
    않는다 — "시간 겹침 없음"을 LLM이 지켜야 할 규칙이 아니라 코드가 보장하는
    성질로 만든다.
    """
    if not places:
        return []
    start, end = time_range
    window_minutes = int((end - start).total_seconds() // 60)
    n = len(places)
    coords = _coords_by_title(place_candidates or [])
    matched_tags = _matched_tag_by_title(place_candidates or [])
    source_categories = _source_category_by_title(place_candidates or [])
    meal_anchors = _meal_anchor_starts(places, time_range, source_categories)

    buffers = []
    for prev, cur in zip(places, places[1:], strict=False):
        prev_coord, cur_coord = coords.get(prev.name), coords.get(cur.name)
        if prev_coord and cur_coord:
            buffers.append(
                estimate_buffer_minutes(prev_coord[0], prev_coord[1], cur_coord[0], cur_coord[1])
            )
        else:
            buffers.append(_ACTIVITY_BUFFER_MINUTES)

    per_activity = (window_minutes - sum(buffers)) // n
    per_activity = max(min(per_activity, _MAX_ACTIVITY_MINUTES), _MIN_ACTIVITY_MINUTES)

    activities = []
    cursor = start
    for i, place in enumerate(places):
        if i > 0:
            cursor = cursor + timedelta(minutes=buffers[i - 1])
        if anchor_start := meal_anchors.get(i):
            cursor = max(cursor, anchor_start)
        activity_end = cursor + timedelta(minutes=per_activity)
        lat, lng, address = coords.get(place.name, (None, None, ""))
        activities.append(
            ActivityDraft(
                name=place.name,
                category=place.category,
                start_time=cursor.strftime("%H:%M"),
                end_time=activity_end.strftime("%H:%M"),
                price_range_per_person=place.price_range_per_person,
                address=address,
                lat=lat,
                lng=lng,
                matched_tag=matched_tags.get(place.name),
                source_category=source_categories.get(place.name),
            )
        )
        cursor = activity_end
    return activities


def _find_perspective(label: str) -> tuple[str, str]:
    for perspective in PERSPECTIVES:
        if perspective[0] == label:
            return perspective
    raise ValueError(f"알 수 없는 관점: {label}")


def _draft_from_selection(
    selection: CandidateSelectionDraft,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> CandidateDraft:
    corrected = _correct_categories(selection, place_candidates)
    return CandidateDraft(
        title=corrected.title,
        activities=_schedule_places(corrected.places, conditions.time_range, place_candidates),
        rationale=corrected.rationale,
    )


async def generate_candidates_with_perspectives(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[tuple[str, CandidateDraft]]:
    """generate_candidates()와 로직은 같지만, 각 CandidateDraft가 어느 관점
    (PERSPECTIVES의 label)에서 나왔는지도 같이 반환한다 — Step3가 후보를 드롭
    했을 때 "그 관점만" 다시 생성하는 재시도(orchestrate.py)가 이 매핑을 알아야
    한다. results가 PERSPECTIVES와 같은 순서로 나온다는 점
    (_call_all_perspectives_sync의 future_to_perspective가 제출 순서를 보존)을
    이용해 zip으로 라벨을 붙인다.
    """
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, _call_all_perspectives_sync, provider, api_key, conditions, place_candidates
    )
    labeled_selections = [
        (perspective[0], r)
        for perspective, r in zip(PERSPECTIVES, results, strict=True)
        if isinstance(r, CandidateSelectionDraft)
    ]
    if not labeled_selections:
        raise RuntimeError("Step2: 3개 관점 호출이 모두 실패했습니다.")
    return [
        (label, _draft_from_selection(selection, conditions, place_candidates))
        for label, selection in labeled_selections
    ]


async def generate_candidates(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[CandidateDraft]:
    """PERSPECTIVES 각각에 대해 스레드풀로 병렬 LLM 호출, CandidateDraft 최대 3개 반환.

    place_candidates: 네이버 지역검색으로 사전 조회한 "지역 내 카테고리별 장소 후보
    목록" — LLM이 이 목록 안에서만 장소를 선택하도록 프롬프트에 주입해 환각을 막는다
    (기술설계 §4 Step 2). 이 함수 밖(장래 POST /schedules 라우터)에서 조회해서
    넘겨야 한다 — Step2는 "조건+장소 후보 → LLM 호출"만 하는 순수 함수로 유지해
    유닛 테스트가 네트워크 mock 없이 call_structured만 mock하면 되게 한다.

    conditions.liked_tags/disliked_tags는 PreferenceTag(tag, verifiable) 리스트다.
    verifiable=true는 하드 제약(반드시 반영/배제), verifiable=false는 소프트 신호
    (참고만, rationale도 hedge된 표현)로 프롬프트에서 다르게 지시한다(2026-08-07 결정).

    관점 3개 중 일부가 timeout(180초)이나 예외로 실패하면 해당 관점만 스킵하고
    나머지로 진행한다. 3개 다 실패하면 RuntimeError.

    LLM은 장소 선택(CandidateSelectionDraft)까지만 하고, 시간 배정은
    _schedule_places()가 결정론적으로 채운다(2026-08-09 결정) — category 재보정
    (_correct_categories)도 그대로 유지.

    관점 라벨이 필요하면 generate_candidates_with_perspectives()를 대신 쓸 것 —
    이 함수는 그 얇은 래퍼다.
    """
    labeled = await generate_candidates_with_perspectives(
        provider, api_key, conditions, place_candidates
    )
    return [draft for _, draft in labeled]


def generate_single_candidate(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
    perspective_label: str,
) -> CandidateDraft:
    """관점 하나만 다시 생성한다 — Step3가 특정 관점의 후보를 하드 위반으로
    드롭했을 때 그 관점만 재시도하는 데 쓴다(orchestrate.py). 새 로직이 아니라
    _call_all_perspectives_sync가 관점 3개에 각각 하던 걸 관점 1개로 좁혀 그대로
    재사용한 것 — 스레드풀 없이 동기 호출 1번(단일 호출이라 병렬화할 대상이
    없음, normalize_conditions와 같은 이유로 sync def).

    _tag_bundles_by_perspective()도 같은 인덱스로 다시 계산해서 써야 한다
    (2026-08-11) — 안 그러면 재시도가 원래 관점 몫이 아니었던 태그 매칭 장소를
    보게 돼서, 재생성한 후보가 다른 관점과 다시 겹칠 수 있다.
    """
    perspective = _find_perspective(perspective_label)
    index = PERSPECTIVES.index(perspective)
    per_perspective_candidates = _tag_bundles_by_perspective(place_candidates, len(PERSPECTIVES))
    selection = call_structured(
        provider=provider,
        api_key=api_key,
        model=get_model(provider, TIER),
        system=_build_system_prompt(perspective),
        user=_build_user_prompt(conditions, per_perspective_candidates[index]),
        schema=CandidateSelectionDraft,
    )
    return _draft_from_selection(selection, conditions, place_candidates)

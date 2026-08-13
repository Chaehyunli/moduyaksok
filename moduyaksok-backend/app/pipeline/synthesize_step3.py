# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 3 — 검증·병합 (MoA Aggregator). 단일 LLM 호출로 3개 후보를
#              최종 확정한다. 랭킹은 매기지 않음 — 동등한 선택지 3개로 제시.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 후보 간 유사도 검사(규칙 기반 사전 계산 + LLM 컨텍스트 주입) 설계
#             추가, "랭킹 없음" 명시 — why_recommended는 순위 근거가 아니라
#             각 후보의 강점 설명
# 2026-08-10, 파일명을 synthesize_step4.py -> synthesize_step3.py로 변경, 이
#             단계가 이동 동선 보강(enrich_routes)보다 먼저 실행되도록 파이프라인
#             순서 재설계(Step1→2→3→사용자 선택→4, docs/AI파이프라인_Step별_설계
#             "전체 흐름" 참고) — 이 단계는 Step2의 장소·시간 데이터만으로 검증
#             가능해(경로 데이터 불필요) 먼저 돌려도 되고, 그래야 사용자가 볼
#             후보 1개에만 나중에 경로(ODsay)를 조회해 비용을 아낄 수 있다.
#             입력 타입도 EnrichedCandidate(경로 포함, 옛 가정) -> CandidateDraft로
#             변경.
# 2026-08-10, 실제 구현. 설계 확정 사항:
#             - 시그니처에 conditions: NormalizedConditions 추가 — 원래 스텁엔
#               없었는데, 예산/시간 위반 재검증에 budget_per_person/time_range가
#               필요해서 빠뜨릴 수 없었다.
#             - "장소 환각" 판단은 별도 place_candidates 조회 없이
#               ActivityDraft.lat이 None인지로 대신한다 — Step2가 place_candidates에
#               없는 이름은 좌표를 못 붙이므로(generate_step2._coords_by_title
#               참고) 이미 있는 신호를 재사용, 새 입력을 안 늘렸다.
#             - 활동 간 시간 겹침은 Step2._schedule_places()가 순차 배정이라
#               구조적으로 이미 불가능하지만, 방어적으로 다시 확인한다(하드 위반).
#             - 관용 범위: 시간 초과 60분, 예산 초과 20% — 기술설계/AI파이프라인
#               설계 문서에 "실측하며 확정"으로 남겨뒀던 값을 여기서 확정. 60분은
#               travel_estimate.py의 재조정 임계값과 같은 수치라 이 프로젝트의
#               "사소한 오차 허용선" 감각과 맞춤.
#             - verifiable=true 태그 위반 판단과 why_recommended 생성은 LLM 1회
#               호출로 처리 — category/name 문자열이 태그와 의미적으로 겹치는지는
#               규칙만으로 못 잡는다(예: "해산물" 태그와 "이자카야" 카테고리).
#             - ponytail: 하드 위반 후보의 "재생성 최대 1회"는 이번 구현에서
#               뺐다 — 재생성하려면 place_candidates와 "이 후보가 어느 관점에서
#               나왔는지"를 이 함수까지 새로 들고 와야 해서 Step2/Step3 사이
#               결합이 커진다. 지금은 위반 후보를 드롭만 하고, "후보 개수는 3개를
#               억지로 보장하지 않는다"(2026-08-09 결정)로 커버한다. 재생성은
#               나중에 라우터 레벨에서 "Step3가 후보를 드롭했다"는 신호를 보고
#               Step2를 그 관점만 다시 불러 붙이는 방향으로 추가할 것.
#             - normalize_conditions(Step1)처럼 LLM 호출이 1회뿐이고 병렬화가
#               필요 없어서 async가 아니라 일반 def로 둔다(기존 스텁은 async였음).
# 2026-08-11, _rule_based_filter에 하드 룰 2개 추가(2026-08-10 미해결 설계 질문 (a)
#             해소 + 지역 간·지역 내 이동거리 문제):
#             - _has_duplicate_tag_match: 같은 verifiable liked_tags 태그를 만족한
#               활동(ActivityDraft.matched_tag)이 한 후보에 2곳 이상이면 하드 위반.
#               generate_step2._ROLE_TASK에 "태그당 최대 1곳" 지시를 추가했지만,
#               이 프로젝트의 기존 원칙("LLM에게 한 번에 너무 많이 시키지 말고
#               결정론적으로 계산 가능한 부분은 코드로 떼어내라")대로 프롬프트만
#               믿지 않고 여기서 한 번 더 하드하게 강제한다.
#             - _has_excessive_travel: 활동 간 좌표(lat/lng) 기준 추정 이동시간
#               (travel_estimate.estimate_buffer_minutes 재사용)이 임계값을 넘으면
#               하드 위반 — "여러 지역을 입력했을 때 서로 먼 지역끼리 하루 코스로
#               섞이는" 문제와 "세부지역 없는 광역 시/도가 여러 세부지역으로
#               확장되면서 그 안에서도 먼 지역끼리 섞이는" 문제를 같은 메커니즘
#               하나로 커버한다 — 활동에 이미 결정론적으로 붙어있는 좌표만 보고
#               판단하므로 "이 활동이 어느 입력 지역/세부지역에서 왔는지"를 따로
#               추적할 필요가 없다. 임계값(_MAX_TRAVEL_MINUTES)은 이 프로젝트가
#               다른 곳(시간 초과 관용 범위)에서 이미 쓰는 60분 감각을 그대로
#               가져온 초기값 — 실제 몇 개 케이스로 실측 후 조정할 것.
# 2026-08-11, _has_missing_meal_slot 추가 — 강한 liked_tag(예: "와플")가 있으면
#             디저트/카페만으로 일정이 채워지고 점심·저녁이 아예 없는 경우가
#             있었다(사용자 관측). time_range가 점심(12~13시)/저녁(18~19시)
#             시간대를 포함하는데 그 시간대와 겹치는 '맛집' 카테고리 활동
#             (ActivityDraft.source_category, generate_step2.py 참고)이 없으면
#             하드 위반. generate_step2._meal_slot_instruction()이 먼저 프롬프트로
#             지시하지만(1차), "태그당 1곳" 때와 같은 이유로 여기서 한 번 더
#             결정론적으로 강제한다(2차).
# 2026-08-11(3차), 사용자 관측상 30분 직선거리 기반 추정 상한도 실제 지도에서
#             동선이 넓게 보였음. 후보군 반경 1.5km화와 함께 연속 구간 상한을
#             15분으로 강화해, 실제 대중교통 이동이 약 30분인 구간도 미리 제외.
# 2026-08-12, TIER를 HIGH -> MID로 내렸다가 바로 되돌림 — "step 로직에서는
#             HIGH(opus급)를 쓰지 않는다"는 방향으로 MID(claude-sonnet-5)로
#             내려서 golden_step3.py 4케이스를 재검증했더니 4개 중 3개가
#             _JudgmentBatch 스키마 검증에서 크래시(ERROR, 평균 점수 0.20).
#             원인은 Claude tool_use가 "judgments": [...] 자리에 리스트 대신
#             그 리스트를 JSON 문자열로 이중 인코딩해서 반환하는 것 — HIGH(opus)
#             에서도 드물게(2회 실행 중 0~1/4) 같은 증상이 있었지만 MID(sonnet)
#             에서는 발생률이 75%로 훨씬 높았다. 이 단계는 판단 품질이 아니라
#             "스키마를 지키는 신뢰성" 자체가 모델 크기에 비례해서 나빠지는
#             것으로 보여 HIGH로 원복 — Step1/Step2와 달리 이 스텝은 아직 MID로
#             못 내린다. 근본 수정은 call_structured()의 anthropic 분기가 list
#             타입 필드에 문자열이 오면 json.loads()로 한 번 더 풀어보는 방어
#             로직을 넣는 것일 텐데, 그건 아직 안 함 — 다음에 이 스텝을 다시
#             내리려면 그 수정부터 하고 재검증할 것.
# 2026-08-12(2차), Step2가 후보별로 확정한 required_meal_tags/
#             required_non_meal_tags를 Step3의 규칙 기반 필터에서도 재검증.
#             간식·체험 태그는 어느 활동에서든 실제 검색 매칭이 있으면 되고,
#             식사 태그는 서로 다른 식사 슬롯·활동에 배정돼야 한다. 여러 태그에
#             함께 매칭된 장소도 ActivityDraft.matched_tags 전체를 보존·검사해
#             LLM 프롬프트만으로 선호를 보장하던 빈틈을 제거했다.
# 2026-08-12(3차), Step2의 후보별 실제 장소 앵커(required_tag_anchors)를 하드
#             검증에 추가. 태그만 같고 다른 가게를 선택하면 해당 후보를 드롭한다.
#             식사 슬롯도 새 후보에는 앵커 장소를 우선 근거로 삼아, "햄버거" 검색
#             결과에 섞여 들어온 카페가 식사로 오인되는 것을 막는다.
# ------------------------------------------------------------------
import logging
from datetime import datetime, time

from pydantic import BaseModel

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import (
    Activity,
    ActivityDraft,
    Candidate,
    CandidateDraft,
    InfeasibleResponse,
    NormalizedConditions,
    PreferenceTag,
    ScheduleResponse,
)
from app.pipeline.travel_estimate import estimate_buffer_minutes
from app.services.naver_map_url import build_naver_map_url
from app.services.structured_llm import call_structured

logger = logging.getLogger(__name__)

# 파이프라인에서 정확한 판단력이 품질을 가장 크게 좌우하는 단계(예산/시간 위반
# 재검증, 후보 드롭·재생성 판단, 최종 요약 작성) — 호출은 1회뿐이라 비용 부담도
# 적어 가장 강한 모델을 쓴다. HIGH 티어. 2026-08-12에 MID로 내렸다가 Claude에서
# _JudgmentBatch 스키마 크래시가 75%까지 뛰어서 바로 원복(위 변경사항 내역 참고)
# — 이 단계는 Step1/Step2와 달리 아직 HIGH가 필요하다.
TIER = ModelTier.HIGH

# 관용 범위 — "무엇이 엄격/관대인가"(docs/AI파이프라인_Step별_설계 Step3 절) 확정값.
_TIME_OVERRUN_TOLERANCE_MINUTES = 60
_BUDGET_OVERRUN_TOLERANCE_RATIO = 0.4
# 한 지역 안에서도 30분은 "동선이 좋은 일정"으로 보기엔 너무 느슨하다. Step2가
# 관점별 입력 자체를 1.5km 근거리 묶음으로 제한한 뒤, 여기서는 연속 구간이 15분을
# 넘으면 하드 드롭한다. 선택 후보 하나에만 실제 길찾기를 하는 구조라 이 시점의
# 직선거리 추정은 여전히 근사치지만, 멀리 퍼진 후보를 사용자에게 노출하지 않는
# 보수적인 상한으로 쓴다.
_MAX_TRAVEL_MINUTES = 15
# 식사 슬롯 판단 기준 — generate_step2.py에도 같은 상수·로직이 독립적으로 있다
# (이 프로젝트 관례상 파이프라인 단계끼리는 서로 안 부르고, 작은 헬퍼는 각자
# 파일에 둔다 — _format_tags()도 이미 두 파일에 각각 있음).
_LUNCH_WINDOW = (time(12, 0), time(13, 0))
_DINNER_WINDOW = (time(18, 0), time(19, 0))
# naver_local_search._PLACE_CATEGORIES 중 "식사가 되는" 카테고리 — 그쪽과 같은
# 목록을 독립적으로 유지한다(위 주석과 같은 이유). 카테고리 목록을 바꿀 땐
# 두 파일(naver_local_search.py, generate_step2.py) 다 같이 확인할 것.
_MEAL_CATEGORIES = frozenset({"한식", "중식", "일식", "양식", "분식", "고깃집"})
# 이 이상 자카드 유사도면 LLM 프롬프트에 "겹치는 후보" 컨텍스트로 얹는다.
_SIMILARITY_CONTEXT_THRESHOLD = 0.5

_CANDIDATE_IDS = ("A", "B", "C")


def _similarity_score(a: CandidateDraft, b: CandidateDraft) -> float:
    """두 후보의 활동 이름 겹치는 비율(자카드 유사도). LLM 호출 전에 미리 계산해서
    겹침이 심한 쌍이 있으면 그 정보를 프롬프트 컨텍스트로 얹어 "겹치는 후보는
    차별점을 강조해라"고 지시하는 데 쓴다.
    """
    names_a = {activity.name for activity in a.activities}
    names_b = {activity.name for activity in b.activities}
    if not names_a or not names_b:
        return 0.0
    return len(names_a & names_b) / len(names_a | names_b)


def _has_hallucinated_activity(candidate: CandidateDraft) -> bool:
    required_ids = set(candidate.required_place_ids)
    return any(
        (activity.lat is None or activity.lng is None) and activity.place_id not in required_ids
        for activity in candidate.activities
    )


def _has_time_overlap(candidate: CandidateDraft) -> bool:
    for prev, cur in zip(candidate.activities, candidate.activities[1:], strict=False):
        if datetime.strptime(prev.end_time, "%H:%M") > datetime.strptime(cur.start_time, "%H:%M"):
            return True
    return False


def _activity_matched_tags(activity: ActivityDraft) -> set[str]:
    """구버전 단일 matched_tag도 포함해 전체 검색 매칭 근거를 읽는다."""
    tags = set(activity.matched_tags)
    if activity.matched_tag:
        tags.add(activity.matched_tag)
    return tags


def _has_duplicate_tag_match(candidate: CandidateDraft) -> bool:
    """같은 좋아요 태그의 일반 활동이 한 후보에 2곳 이상이면 하드 위반.

    한 장소가 여러 검색 태그에 동시에 잡힌 경우도 모두 검사한다. 예를 들어 첫
    장소가 스시/초밥이고 두 번째가 스시면, 스시를 중복 반영한 것으로 본다. 단,
    사용자가 같은 태그의 장소를 여러 곳 직접 필수로 골랐다면 그 필수 개수까지만
    허용한다. 필수 한 곳이 태그를 이미 충족했다고 일반 장소까지 더 허용하지 않는다.
    """
    total_counts: dict[str, int] = {}
    required_counts: dict[str, int] = {}
    required_ids = set(candidate.required_place_ids)
    for activity in candidate.activities:
        tags = _activity_matched_tags(activity)
        for tag in tags:
            total_counts[tag] = total_counts.get(tag, 0) + 1
            if activity.place_id in required_ids:
                required_counts[tag] = required_counts.get(tag, 0) + 1
    return any(count > max(1, required_counts.get(tag, 0)) for tag, count in total_counts.items())


def _has_duplicate_place(candidate: CandidateDraft) -> bool:
    """같은 장소(activity.name)가 한 후보에 2번 이상 등장하면 하드 위반
    (2026-08-12(2차)). generate_step2._dedupe_places()가 1차로 걸러내지만,
    "프롬프트만 믿지 말고 결정 가능한 건 코드로 2차 강제"라는 이 프로젝트
    원칙(_has_duplicate_tag_match와 같은 결)을 그대로 적용 — matched_tag가
    없는(태그 매칭 없이 카테고리로만 고른) 장소가 중복되는 경우까지 잡는다.
    """
    seen: set[str] = set()
    for activity in candidate.activities:
        if activity.name in seen:
            return True
        seen.add(activity.name)
    return False


def _has_excessive_travel(candidate: CandidateDraft) -> bool:
    """연속된 두 활동 사이 추정 이동시간이 임계값을 넘으면 하드 위반 — 여러
    지역을 입력했을 때 서로 먼 지역끼리(예: 서울 강남 + 경기 수원) 하루 코스로
    섞이거나, 세부지역 없는 광역 시/도가 여러 세부지역으로 확장되면서 그 안에서도
    먼 지역끼리 섞이는 문제를 잡는다. 좌표가 없는 활동(환각 장소, 이미
    _has_hallucinated_activity가 먼저 드롭함)은 건너뛴다.
    """
    required_ids = set(candidate.required_place_ids)
    for prev, cur in zip(candidate.activities, candidate.activities[1:], strict=False):
        if prev.lat is None or prev.lng is None or cur.lat is None or cur.lng is None:
            continue
        minutes = estimate_buffer_minutes(prev.lat, prev.lng, cur.lat, cur.lng)
        involves_required_place = bool(
            required_ids and (prev.place_id in required_ids or cur.place_id in required_ids)
        )
        if minutes > _MAX_TRAVEL_MINUTES and not involves_required_place:
            return True
    return False


def _required_travel_warning_minutes(candidate: CandidateDraft) -> int:
    """거리 필터를 면제한 필수 장소 연결 구간 중 가장 긴 예상 이동시간."""
    required_ids = set(candidate.required_place_ids)
    longest = 0
    if not required_ids:
        return longest
    for prev, cur in zip(candidate.activities, candidate.activities[1:], strict=False):
        if prev.lat is None or prev.lng is None or cur.lat is None or cur.lng is None:
            continue
        if prev.place_id not in required_ids and cur.place_id not in required_ids:
            continue
        longest = max(
            longest,
            estimate_buffer_minutes(prev.lat, prev.lng, cur.lat, cur.lng),
        )
    return longest if longest > _MAX_TRAVEL_MINUTES else 0


def _required_meal_windows(time_range: tuple[datetime, datetime]) -> list[tuple[time, time]]:
    """time_range가 점심(12~13시)/저녁(18~19시) 구간을 포함하면 그 구간을 필수
    식사 슬롯으로 반환한다 — generate_step2._required_meal_windows()와 같은 로직.
    """
    start, end = time_range
    windows: list[tuple[time, time]] = []
    if start.time() <= _LUNCH_WINDOW[0] and end.time() >= _LUNCH_WINDOW[1]:
        windows.append(_LUNCH_WINDOW)
    if start.time() <= _DINNER_WINDOW[0] and end.time() >= _DINNER_WINDOW[1]:
        windows.append(_DINNER_WINDOW)
    return windows


def _has_missing_meal_slot(candidate: CandidateDraft, conditions: NormalizedConditions) -> bool:
    """time_range가 점심/저녁 시간대를 포함하는데 그 시간대와 겹치는 식사류
    카테고리 활동(ActivityDraft.source_category)이 없으면 하드 위반 — 강한
    liked_tag가 있을 때 디저트/카페만으로 일정이 채워지는 문제 대응.
    """
    meal_tags = {tag.tag for tag in conditions.liked_tags if tag.verifiable and tag.is_meal}
    required_meal_anchors = {
        candidate.required_tag_anchors[tag]
        for tag in candidate.required_meal_tags
        if tag in candidate.required_tag_anchors
    }
    for slot_start, slot_end in _required_meal_windows(conditions.time_range):
        has_meal = any(
            (
                activity.source_category in _MEAL_CATEGORIES
                or activity.name in required_meal_anchors
                # 구버전 CandidateDraft에는 구체 앵커가 없으므로 기존 태그 매칭
                # 기준으로 폴백한다.
                or (
                    not required_meal_anchors and bool(_activity_matched_tags(activity) & meal_tags)
                )
            )
            and datetime.strptime(activity.start_time, "%H:%M").time() < slot_end
            and datetime.strptime(activity.end_time, "%H:%M").time() > slot_start
            for activity in candidate.activities
        )
        if not has_meal:
            return True
    return False


def _has_excessive_meal_places(candidate: CandidateDraft, conditions: NormalizedConditions) -> bool:
    """식사 시간대 수보다 식사 장소가 과도하게 많이 선택됐는지 검사한다.

    점심·저녁이 모두 있는 일정은 보통 식사 두 곳이면 충분하다. 같은 식사 태그를
    좋아했다는 이유로 세 곳 이상을 채우지 못하게 하되, 사용자가 직접 필수로 고른
    식사 장소 수가 더 많다면 그 선택은 그대로 허용한다.
    """
    meal_tags = {tag.tag for tag in conditions.liked_tags if tag.verifiable and tag.is_meal}

    def is_meal(activity: ActivityDraft) -> bool:
        return activity.source_category in _MEAL_CATEGORIES or bool(
            _activity_matched_tags(activity) & meal_tags
        )

    meal_activities = [activity for activity in candidate.activities if is_meal(activity)]
    required_ids = set(candidate.required_place_ids)
    required_meal_count = sum(activity.place_id in required_ids for activity in meal_activities)
    allowed = max(
        1,
        len(_required_meal_windows(conditions.time_range)),
        required_meal_count,
    )
    return len(meal_activities) > allowed


def _has_missing_required_tags(candidate: CandidateDraft, conditions: NormalizedConditions) -> bool:
    """Step2가 후보마다 정한 태그 제약을 실제 선택 결과에서 다시 강제한다.

    비식사 태그는 일정의 어느 활동에서든 한 번이면 충분하다. 식사 태그는 각기
    다른 활동·식사 슬롯에 배정될 수 있어야 한다. 따라서 LLM이 프롬프트의 "반드시"
    지시를 놓쳐도 Step3에서 통과하지 못한다.
    """
    matched_by_activity = [_activity_matched_tags(activity) for activity in candidate.activities]
    if not set(candidate.required_non_meal_tags).issubset(
        {tag for tags in matched_by_activity for tag in tags}
    ):
        return True

    required_meal_tags = tuple(candidate.required_meal_tags)
    if not required_meal_tags:
        return False

    # Step2의 시간 배정기가 식사 활동을 점심/저녁 창에 앵커링하므로, 실제 결과도
    # 해당 태그가 서로 다른 식사 슬롯 안에 있는지만 결정론적으로 검사하면 된다.
    slots = _required_meal_windows(conditions.time_range)
    if len(required_meal_tags) > len(slots):
        return True
    options: list[list[tuple[int, int]]] = []
    for tag in required_meal_tags:
        matches: list[tuple[int, int]] = []
        for activity_index, activity in enumerate(candidate.activities):
            if tag not in matched_by_activity[activity_index]:
                continue
            start = datetime.strptime(activity.start_time, "%H:%M").time()
            end = datetime.strptime(activity.end_time, "%H:%M").time()
            for slot_index, (slot_start, slot_end) in enumerate(slots):
                if start < slot_end and end > slot_start:
                    matches.append((activity_index, slot_index))
        if not matches:
            return True
        options.append(matches)

    def assign(index: int, used_activities: set[int], used_slots: set[int]) -> bool:
        if index == len(options):
            return True
        return any(
            activity_index not in used_activities
            and slot_index not in used_slots
            and assign(
                index + 1,
                used_activities | {activity_index},
                used_slots | {slot_index},
            )
            for activity_index, slot_index in options[index]
        )

    return not assign(0, set(), set())


def _has_insufficient_preference_coverage(
    candidate: CandidateDraft, conditions: NormalizedConditions
) -> bool:
    """검증 가능한 좋아요 태그는 가능한 범위에서 과반수 반영해야 한다.

    식사 태그의 시간대·서로 다른 슬롯 배정 규칙은 _has_missing_required_tags()가
    별도로 계속 강제한다. 식사 선호가 식사 슬롯보다 많을 때는 가능한 슬롯 수를
    상한으로 두고, 여기서는 식사/비식사를 합친 전체 선호 충족률을 본다.
    """
    liked_tags = {tag.tag for tag in conditions.liked_tags if tag.verifiable}
    meal_tags = {tag.tag for tag in conditions.liked_tags if tag.verifiable and tag.is_meal}
    non_meal_count = len(liked_tags - meal_tags)
    meal_capacity = max(1, len(_required_meal_windows(conditions.time_range)))
    feasible_count = non_meal_count + min(len(meal_tags), meal_capacity)
    minimum_coverage = min(len(liked_tags) // 2 + 1, feasible_count)
    if minimum_coverage == 0:
        return False

    # 구버전 저장 세션·단위 테스트처럼 Step2 계획 정보가 전혀 없는 초안에는
    # 새 규칙을 소급 적용할 근거가 없다. 새 생성 흐름은 최소 태그 앵커를 반드시
    # 넣으므로 이 분기 없이 아래 검증을 탄다.
    if not candidate.required_meal_tags and not candidate.required_non_meal_tags:
        return False

    matched_tags = set(candidate.precovered_liked_tags) | {
        tag for activity in candidate.activities for tag in _activity_matched_tags(activity)
    }
    return len(liked_tags & matched_tags) < minimum_coverage


def _has_missing_required_anchors(candidate: CandidateDraft) -> bool:
    """후보별로 고정한 실제 태그 장소가 LLM 선택에 남아 있는지 확인한다.

    태그만 같은 다른 가게로 바꾸는 것은 각 후보의 다양성을 다시 무너뜨린다. 예를
    들어 후보 A에 햄버거→데일리픽스, B에 햄버거→위트앤미트가 배정됐다면 둘 다
    해당 정확한 장소를 포함해야 한다.
    """
    return not set(candidate.required_tag_anchors.values()).issubset(
        {activity.name for activity in candidate.activities}
    )


def _has_missing_required_places(candidate: CandidateDraft) -> bool:
    """사용자가 고른 장소가 실제 결과에 빠지면 후보를 무조건 드롭한다.

    후보 풀에 추가되기만 하고 LLM 선택에서 빠지는 것을 막는 마지막 방어선이다.
    이름은 동명 지점이 있을 수 있어 ``ActivityDraft.place_id``로 비교한다.
    """
    return not set(candidate.required_place_ids).issubset(
        {activity.place_id for activity in candidate.activities if activity.place_id}
    )


def _budget_overrun_ratio(candidate: CandidateDraft, budget_per_person: int) -> float:
    total = sum(a.price_range_per_person[0] for a in candidate.activities)
    if budget_per_person <= 0:
        return 0.0
    return max(0.0, total - budget_per_person) / budget_per_person


def _time_overrun_minutes(candidate: CandidateDraft, time_range: tuple[datetime, datetime]) -> int:
    if not candidate.activities:
        return 0
    _, window_end = time_range
    last_end_time = datetime.strptime(candidate.activities[-1].end_time, "%H:%M").time()
    last_end = datetime.combine(window_end.date(), last_end_time)
    return max(0, int((last_end - window_end).total_seconds() // 60))


def _rule_based_filter(
    candidates: list[CandidateDraft], conditions: NormalizedConditions
) -> tuple[list[CandidateDraft], list[str]]:
    """LLM 호출 전에 결정론적으로 판단 가능한 하드 위반만 걸러낸다 — 장소 환각,
    활동 간 시간 겹침, 같은 태그 중복 반영, 같은 장소 중복 방문, 과도한 이동거리,
    식사 슬롯 누락(여섯 다 예외 없이 드롭), 예산/시간 대폭 초과(관용 범위
    초과분만 드롭). 관용 범위 이내의 예산/시간 초과는 드롭하지 않고 경고 문구를
    만들어 survivors와 같은 순서로 돌려준다(경고 없으면 빈 문자열) —
    synthesize_and_validate가 LLM의 feasibility_note와 합쳐 최종
    feasibility_warning을 만든다.
    """
    survivors: list[CandidateDraft] = []
    warnings: list[str] = []
    for candidate in candidates:
        if (
            _has_hallucinated_activity(candidate)
            or _has_time_overlap(candidate)
            or _has_duplicate_tag_match(candidate)
            or _has_duplicate_place(candidate)
            or _has_excessive_travel(candidate)
            or _has_missing_meal_slot(candidate, conditions)
            or _has_excessive_meal_places(candidate, conditions)
            or _has_missing_required_tags(candidate, conditions)
            or _has_insufficient_preference_coverage(candidate, conditions)
            or _has_missing_required_anchors(candidate)
            or _has_missing_required_places(candidate)
        ):
            continue

        budget_ratio = _budget_overrun_ratio(candidate, conditions.budget_per_person)
        overrun_minutes = _time_overrun_minutes(candidate, conditions.time_range)
        if not candidate.required_place_ids and (
            budget_ratio > _BUDGET_OVERRUN_TOLERANCE_RATIO
            or overrun_minutes > _TIME_OVERRUN_TOLERANCE_MINUTES
        ):
            continue

        warning_parts = []
        if budget_ratio > 0:
            over_amount = int(conditions.budget_per_person * budget_ratio)
            warning_parts.append(f"1인 예산보다 약 {over_amount}원 더 필요할 수 있어요")
        if overrun_minutes > 0:
            warning_parts.append(f"예정보다 약 {overrun_minutes}분 더 걸릴 수 있어요")
        if required_travel_minutes := _required_travel_warning_minutes(candidate):
            warning_parts.append(
                "고정된 장소를 포함해 한 구간 이동이 "
                f"약 {required_travel_minutes}분 이상 걸릴 수 있어요"
            )
        missing_required_coordinates = [
            activity.name
            for activity in candidate.activities
            if activity.place_id in set(candidate.required_place_ids)
            and (activity.lat is None or activity.lng is None)
        ]
        if missing_required_coordinates:
            warning_parts.append(
                f"고정된 장소({', '.join(missing_required_coordinates)})의 위치를 "
                "자동 확인하지 못해 이동 경로를 직접 확인해야 해요"
            )

        survivors.append(candidate)
        warnings.append(", ".join(warning_parts))
    return survivors, warnings


def _to_activities(drafts: list[ActivityDraft]) -> list[Activity]:
    """ActivityDraft를 최종 Activity로 변환한다. 영업시간은 자동 확인을 포기하고
    (operating_hours="", info_needs_check=True) 네이버 지도 링크로 사용자가 직접
    확인하게 유도한다 — "검증 못 한 걸 확신하는 것처럼 말하지 않는다"는 이
    프로젝트 기존 원칙. lat/lng도 그대로 넘긴다 — Step4(enrich_routes)가 이
    Activity를 받아 구간별 이동 옵션을 조회하는 데 좌표가 필요하다(2026-08-10).
    """
    activities = []
    for i, draft in enumerate(drafts):
        map_url = (
            build_naver_map_url({"title": draft.name, "roadAddress": draft.address})
            if draft.address
            else ""
        )
        activities.append(
            Activity(
                order=i + 1,
                name=draft.name,
                category=draft.category,
                address=draft.address,
                start_time=draft.start_time,
                end_time=draft.end_time,
                price_range_per_person=draft.price_range_per_person,
                operating_hours="",
                phone=None,
                info_needs_check=True,
                map_url=map_url,
                lat=draft.lat,
                lng=draft.lng,
                matched_tag=draft.matched_tag,
                matched_tags=draft.matched_tags,
                source_category=draft.source_category,
                place_id=draft.place_id,
            )
        )
    return activities


def _infeasible_response() -> InfeasibleResponse:
    return InfeasibleResponse(
        detail="생성 가능한 일정이 없어요 ㅠㅠ 조건을 다시 설정해주세요.",
        reason="예산·시간대·지역 조건에 맞는 일정을 만들지 못했습니다.",
        adjustable_conditions=["budget_per_person", "time_range", "region"],
    )


def _format_tags(tags: list[PreferenceTag]) -> str:
    if not tags:
        return "(없음)"
    return ", ".join(f"{t.tag}(verifiable={t.verifiable}, is_meal={t.is_meal})" for t in tags)


_ROLE_TASK = """\
# Role
너는 이미 결정론적 조건 검증을 통과한 만남 일정 후보들의 제목과 설명을 다듬는 \
전문 에디터다.

# Task
- 후보를 삭제하거나 장소·순서·시간을 바꾸지 마라. 모든 후보는 keep=true다.
- verifiable=false인 태그(liked/disliked 모두)는 확인할 방법이 없는 주관적 \
취향이니 확정적 사실처럼 쓰지 마라.
- title은 장소 목록을 잘 나타내면서 후보끼리 구분되는 짧은 일정 제목으로 써라.
- keep=true인 후보에는 why_recommended를 써라 — "다른 후보보다 나아서"가 아니라 \
"이 후보만의 강점이 뭔지"를 한두 문장으로 설명해라(랭킹 아님, 참고할 rationale \
필드가 있다).
- similar_candidate_pairs로 겹침이 심하다고 표시된 후보 쌍이 있으면, 그 후보들의 \
why_recommended에서 서로 다른 점을 강조해서 써라.
- feasibility_note는 이 후보에 대해 사용자에게 추가로 알려줄 주의사항이 있으면 \
한 문장으로 써라(없으면 빈 문자열). 확인 못 한 걸 확신하는 것처럼 쓰지 마라 — \
"사람이 없습니다"가 아니라 "비교적 한산한 편일 수 있어요"처럼 hedge된 표현을 써라.

# Format
입력에 있는 candidate_index(0부터, 입력 순서 그대로)마다 title/keep/\
why_recommended/feasibility_note를 하나씩 채워라. keep은 항상 true다.\
"""


class _CandidateJudgment(BaseModel):
    candidate_index: int
    title: str = ""
    keep: bool
    why_recommended: str
    feasibility_note: str


class _JudgmentBatch(BaseModel):
    judgments: list[_CandidateJudgment]


def _build_user_prompt(
    conditions: NormalizedConditions,
    candidates: list[CandidateDraft],
    similar_pairs: list[tuple[int, int, float]],
) -> str:
    lines = [
        f"1인 예산: {conditions.budget_per_person}원",
        f"좋아하는 것: {_format_tags(conditions.liked_tags)}",
        f"싫어하는 것: {_format_tags(conditions.disliked_tags)}",
        "",
        "후보 목록:",
    ]
    for i, candidate in enumerate(candidates):
        lines.append(f"[candidate_index={i}] {candidate.title}")
        lines.append(f"  관점 근거(rationale): {candidate.rationale}")
        for activity in candidate.activities:
            lines.append(f"  - {activity.name} ({activity.category})")

    if similar_pairs:
        pairs_text = ", ".join(f"{i}번-{j}번(유사도 {score:.2f})" for i, j, score in similar_pairs)
        lines.append("")
        lines.append(f"similar_candidate_pairs: {pairs_text}")

    return "\n".join(lines)


def synthesize_and_validate(
    provider: str,
    api_key: str,
    session_id: str,
    conditions: NormalizedConditions,
    candidates: list[CandidateDraft],
) -> ScheduleResponse | InfeasibleResponse:
    """Step2에서 나온 (최대 3개) 초안(장소·순서·시간은 이미 확정됨, 이동 경로는
    아직 없음 — Step4가 사용자 선택 이후에 채운다)을 검증해 최종 3개(또는 그
    이하)로 확정한다. 구조(장소·순서·시간)는 재배치하지 않는다:
    1. 규칙 기반 사전 필터링(_rule_based_filter) — 장소 환각·시간 겹침·같은 태그
       중복 반영·과도한 이동거리·식사 슬롯 누락은 예외 없이 드롭, 예산/시간 초과는 관용 범위
       (40%/60분) 넘을 때만 드롭
    2. 후보 간 유사도 검사(_similarity_score) — LLM 호출 전에 미리 계산해서
       겹침이 심한 쌍이 있으면 프롬프트 컨텍스트로 얹음
    3. 살아남은 후보 전부를 한 번의 LLM 호출에 넣어 title·why_recommended와
       feasibility_note 작성. AI 응답 누락이나 keep=false는 후보를 드롭하지 않음
    4. 규칙 기반 경고(예산/시간 관용 범위 내 초과)와 LLM의 feasibility_note를
       합쳐 최종 feasibility_warning으로 채움

    왜 후보마다 따로 호출하지 않고 1번에 다 넣는가: "후보끼리 비교"(유사도 기반
    차별점 강조)가 이 단계의 핵심 역할 중 하나라, 후보를 하나씩 따로 호출하면
    다른 후보를 볼 방법이 없다.

    랭킹을 매기지 않는다 — 3개는 서로 다른 관점(가성비/동선최소화/취향반영)으로
    만들어진 것이라 "AI가 뽑은 1등"이 아니라 동등한 선택지로 제시한다.
    candidate_id도 숫자가 아니라 A/B/C 문자를 쓴다(개수만큼만 부여).

    규칙 기반 필터링 이후 살아남은 후보가 하나도 없으면 LLM을 호출하지 않고
    바로 InfeasibleResponse를 반환한다(비용 절약). 하드 규칙을 통과한 뒤에는
    LLM이 최종 후보 수를 줄일 권한을 갖지 않는다.
    """
    rule_survivors, rule_warnings = _rule_based_filter(candidates, conditions)
    if not rule_survivors:
        return _infeasible_response()

    similar_pairs = [
        (i, j, score)
        for i in range(len(rule_survivors))
        for j in range(i + 1, len(rule_survivors))
        if (score := _similarity_score(rule_survivors[i], rule_survivors[j]))
        >= _SIMILARITY_CONTEXT_THRESHOLD
    ]

    try:
        judgment = call_structured(
            provider=provider,
            api_key=api_key,
            model=get_model(provider, TIER),
            system=_ROLE_TASK,
            user=_build_user_prompt(conditions, rule_survivors, similar_pairs),
            schema=_JudgmentBatch,
        )
    except Exception:
        # 이 호출은 이미 규칙을 통과한 일정에 제목·설명을 붙이는 보조 단계다.
        # provider 지연/장애 때문에 유효한 일정 자체를 버리지 않고 draft의 제목과
        # rationale을 아래 기존 폴백 경로로 사용한다.
        logger.exception("일정 설명 생성에 실패해 규칙 기반 결과로 대체합니다.")
        judgment = _JudgmentBatch(judgments=[])

    kept: list[Candidate] = []
    judgment_by_index = {
        entry.candidate_index: entry
        for entry in judgment.judgments
        if 0 <= entry.candidate_index < len(rule_survivors)
    }
    for candidate_index, draft in enumerate(rule_survivors):
        entry = judgment_by_index.get(candidate_index)
        # 하드 드롭 권한은 위 결정론적 필터에만 있다. AI 응답 누락이나 keep=false가
        # 유효한 후보 수를 줄이지 못하게 하고, 설명만 안전하게 폴백한다.
        if len(kept) >= len(_CANDIDATE_IDS):
            break

        rule_warning = rule_warnings[candidate_index]
        feasibility_note = entry.feasibility_note if entry else ""
        why_recommended = entry.why_recommended if entry else draft.rationale
        combined_warning = " ".join(p for p in (rule_warning, feasibility_note) if p)
        kept.append(
            Candidate(
                candidate_id=_CANDIDATE_IDS[len(kept)],
                title=entry.title.strip() if entry and entry.title.strip() else draft.title,
                why_recommended=why_recommended,
                activities=_to_activities(draft.activities),
                routes=[],
                feasibility_warning=combined_warning or None,
            )
        )

    if not kept:
        return _infeasible_response()

    return ScheduleResponse(session_id=session_id, candidates=kept)

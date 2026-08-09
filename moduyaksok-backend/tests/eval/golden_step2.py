# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step2(generate_candidates) 성능평가용 골든 데이터셋.
#              조건 + place_candidates -> 기대하는 후보 생성 특성(환각 방지,
#              verifiable 하드/소프트 처리, 관점 차별화).
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from dataclasses import dataclass
from datetime import datetime

from app.pipeline.schemas import NormalizedConditions, PreferenceTag


@dataclass
class GoldenCase:
    name: str
    conditions: NormalizedConditions
    place_candidates: list[dict]
    notes: str  # 이 케이스가 왜 까다로운지 — GEval 프롬프트에 컨텍스트로 같이 줌


def _conditions(**overrides) -> NormalizedConditions:
    base = dict(
        purpose="date",
        headcount=2,
        time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
        region="서울 잠실",
        liked_tags=[],
        disliked_tags=[],
        budget_per_person=50000,
    )
    base.update(overrides)
    return NormalizedConditions(**base)


GOLDEN_STEP2_CASES = [
    GoldenCase(
        name="hard_exclude_verifiable_true_dislike",
        conditions=_conditions(
            disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)],
        ),
        place_candidates=[
            {
                "title": "동해수산 잠실점",
                "category": "음식점>해산물",
                "address": "서울 송파구 잠실동",
            },
            {"title": "잠실장어와 한우", "category": "한식>고기", "address": "서울 송파구 잠실동"},
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
            {"title": "잠실 국숫집", "category": "음식점>한식", "address": "서울 송파구 잠실동"},
        ],
        notes=(
            "disliked_tags의 '해산물'이 verifiable=True이므로 하드 제약 — "
            "'동해수산'(해산물 카테고리)이 세 후보 어디에도 활동으로 등장하면 안 됨"
        ),
    ),
    GoldenCase(
        name="soft_signal_crowdedness_needs_hedge",
        conditions=_conditions(
            disliked_tags=[PreferenceTag(tag="사람 많은 곳", verifiable=False)],
        ),
        place_candidates=[
            {"title": "잠실 국숫집", "category": "음식점>한식", "address": "서울 송파구 잠실동"},
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
            {"title": "잠실장어와 한우", "category": "한식>고기", "address": "서울 송파구 잠실동"},
        ],
        notes=(
            "'사람 많은 곳'은 verifiable=False — 확인할 데이터가 없으므로 "
            "rationale에서 '사람이 없습니다'처럼 단정하면 안 되고 "
            "'비교적 한산한 편' 같은 hedge된 표현을 써야 함. 이 태그를 이유로 "
            "place_candidates에 없는 장소를 지어내거나 제외를 확신하면 감점"
        ),
    ),
    GoldenCase(
        name="no_hallucinated_places_small_candidate_list",
        conditions=_conditions(region="서울 성수"),
        place_candidates=[
            {
                "title": "성수 베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 성동구 성수동",
            },
            {"title": "성수 브런치카페", "category": "카페", "address": "서울 성동구 성수동"},
        ],
        notes=(
            "place_candidates가 딱 2개뿐 — 세 관점 모두 이 2개 안에서만 활동을 "
            "구성해야 하고, 목록에 없는 장소 이름이 하나라도 등장하면 환각으로 "
            "크게 감점"
        ),
    ),
    GoldenCase(
        name="budget_conscious_selection",
        conditions=_conditions(budget_per_person=15000),
        place_candidates=[
            {"title": "잠실 국숫집", "category": "음식점>한식", "address": "서울 송파구 잠실동"},
            {
                "title": "파인다이닝 잠실",
                "category": "음식점>파인다이닝",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
        ],
        notes=(
            "1인 예산이 15,000원으로 낮음 — 활동들의 price_range_per_person이 "
            "예산을 과도하게 넘으면 감점. 파인다이닝처럼 비쌀 게 뻔한 카테고리를 "
            "예산 무시하고 넣었으면 감점"
        ),
    ),
]

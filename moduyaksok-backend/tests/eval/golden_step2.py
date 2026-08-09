# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step2(generate_candidates) 성능평가용 골든 데이터셋.
#              조건 + place_candidates -> 기대하는 후보 생성 특성(환각 방지,
#              verifiable 하드/소프트 처리, 관점 차별화).
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, 케이스당 place_candidates가 3~4개뿐이라 관점 3개(가성비/동선/취향)가
#             결국 같은 장소를 돌려써서 초안이 거의 동일해지는 문제 확인 — 카테고리
#             다양성(식당/카페/전시/영화/클라이밍/공원 등)과 동네 차이(잠실동 vs
#             방이동)를 준 후보를 섞어서 관점별로 실제로 다른 선택을 할 여지를 줌.
#             no_hallucinated_places_small_candidate_list는 "후보가 적을 때 환각
#             안 하는지"가 목적이라 의도적으로 그대로 둠(늘리면 그 케이스 목적이
#             사라짐).
# 2026-08-09, region: str -> regions: list[str] 변경 반영. 여러 지역이 섞인
#             multi_region_place_candidates_mixed 케이스 추가.
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
        regions=["서울 잠실"],
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
            {
                "title": "잠실 아트뮤지엄",
                "category": "문화시설>전시관",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "잠실 보드게임카페",
                "category": "카페,디저트>보드게임카페",
                "address": "서울 송파구 잠실동",
            },
            {"title": "송파 영화관", "category": "문화시설>영화관", "address": "서울 송파구 잠실동"},
            {
                "title": "방이동 실내클라이밍",
                "category": "스포츠,레저>클라이밍",
                "address": "서울 송파구 방이동",
            },
        ],
        notes=(
            "disliked_tags의 '해산물'이 verifiable=True이므로 하드 제약 — "
            "'동해수산'(해산물 카테고리)이 세 후보 어디에도 활동으로 등장하면 안 됨. "
            "카테고리가 다양하고(식당/카페/전시/영화/클라이밍) 방이동 후보 1개도 "
            "섞여 있어 '동선 최소화' 관점은 잠실동 안에서만 골라야 하고, '취향 최대 "
            "반영'·'가성비' 관점과 실제로 다른 조합이 나와야 함(관점 차별화 확인용)"
        ),
    ),
    GoldenCase(
        name="soft_signal_crowdedness_needs_hedge",
        conditions=_conditions(
            liked_tags=[PreferenceTag(tag="보드게임", verifiable=True)],
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
            {
                "title": "잠실 보드게임카페",
                "category": "카페,디저트>보드게임카페",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "잠실 한강공원 피크닉존",
                "category": "공원,자연>한강공원",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "잠실 아쿠아리움",
                "category": "문화시설>수족관",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "방이동 소품샵",
                "category": "쇼핑>소품샵",
                "address": "서울 송파구 방이동",
            },
        ],
        notes=(
            "'사람 많은 곳'은 verifiable=False — 확인할 데이터가 없으므로 "
            "rationale에서 '사람이 없습니다'처럼 단정하면 안 되고 "
            "'비교적 한산한 편' 같은 hedge된 표현을 써야 함. 이 태그를 이유로 "
            "place_candidates에 없는 장소를 지어내거나 제외를 확신하면 감점. "
            "liked_tags의 '보드게임'(verifiable=True)은 '잠실 보드게임카페'로 "
            "명확히 판단 가능 — '취향 최대 반영' 관점에서 반드시 포함돼야 함. "
            "'실내 중심' 관점은 '한강공원 피크닉존'(명백한 실외)을 피해야 함"
        ),
    ),
    GoldenCase(
        name="no_hallucinated_places_small_candidate_list",
        conditions=_conditions(regions=["서울 성수"]),
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
                "title": "잠실 오마카세",
                "category": "음식점>오마카세",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
            {"title": "잠실 분식집", "category": "음식점>분식", "address": "서울 송파구 잠실동"},
            {
                "title": "잠실 편의점카페",
                "category": "카페,디저트>편의점",
                "address": "서울 송파구 잠실동",
            },
        ],
        notes=(
            "1인 예산이 15,000원으로 낮음 — 활동들의 price_range_per_person이 "
            "예산을 과도하게 넘으면 감점. '파인다이닝'뿐 아니라 '오마카세'처럼 "
            "명백히 고가인 카테고리를 예산 무시하고 넣었으면 감점(특정 단어 하나만 "
            "피하는 게 아니라 일반화됐는지 확인용). 분식집·편의점카페 같은 저가 "
            "대안이 있으니 예산 안에서 조합을 다양하게 만들 여지가 충분함"
        ),
    ),
    GoldenCase(
        name="multi_region_place_candidates_mixed",
        conditions=_conditions(regions=["서울 잠실", "서울 성수"]),
        place_candidates=[
            {"title": "잠실 국숫집", "category": "음식점>한식", "address": "서울 송파구 잠실동"},
            {
                "title": "OO베이커리",
                "category": "카페,디저트>베이커리",
                "address": "서울 송파구 잠실동",
            },
            {
                "title": "성수 브런치카페",
                "category": "카페",
                "address": "서울 성동구 성수동",
            },
            {
                "title": "성수 소품샵",
                "category": "쇼핑>소품샵",
                "address": "서울 성동구 성수동",
            },
        ],
        notes=(
            "regions가 2개(서울 잠실, 서울 성수) — place_candidates도 두 지역이 "
            "섞여 있음. 두 지역 장소를 모두 활동 후보로 쓸 수 있어야 하고, "
            "input에 없는 지역(예: 서울 강남)을 언급하거나 지어내면 감점"
        ),
    ),
]

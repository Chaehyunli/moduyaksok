from datetime import datetime

from app.pipeline.generate_algorithm_step2 import (
    ensure_place_ids,
    generate_algorithm_candidates,
)
from app.pipeline.schemas import NormalizedConditions, PreferenceTag


def _places() -> list[dict]:
    categories = [
        "중식",
        "중식",
        "중식",
        "한식",
        "일식",
        "양식",
        "카페",
        "카페",
        "베이커리",
        "액티비티",
        "방탈출",
        "보드게임카페",
        "전시",
        "전시",
        "전시",
        "공연장",
        "영화관",
        "분식",
    ]
    result = []
    for index, category in enumerate(categories):
        place = {
            "title": f"{category} 장소 {index}",
            "category": category,
            "source_category": category,
            "roadAddress": f"서울 강남구 테스트로 {index}",
            "mapx": str(1_270_000_000 + index * 1_000),
            "mapy": str(375_000_000 + index * 500),
        }
        if index < 3:
            place["matched_tags"] = ["마라탕"]
        if 12 <= index < 15:
            place["matched_tags"] = ["전시"]
        result.append(place)
    return ensure_place_ids(result)


def _conditions() -> NormalizedConditions:
    return NormalizedConditions(
        purpose="date",
        headcount=2,
        time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
        region="서울 강남",
        liked_tags=[
            PreferenceTag(
                tag="마라탕",
                verifiable=True,
                is_meal=True,
                preference_kind="food_menu",
                priority=5,
            ),
            PreferenceTag(
                tag="전시",
                verifiable=True,
                preference_kind="place_type",
                priority=4,
            ),
        ],
        disliked_tags=[],
        budget_per_person=50_000,
    )


def _place_jaccard(left, right) -> float:
    left_ids = {activity.place_id for activity in left.activities}
    right_ids = {activity.place_id for activity in right.activities}
    return len(left_ids & right_ids) / len(left_ids | right_ids)


def test_algorithm_returns_three_valid_and_diverse_candidates():
    labeled = generate_algorithm_candidates("upstage", "unused", _conditions(), _places())

    assert len(labeled) == 3
    drafts = [draft for _, draft in labeled]
    from app.pipeline.synthesize_step3 import _rule_based_filter

    assert len(_rule_based_filter(drafts, _conditions())[0]) == 3
    for draft in drafts:
        assert len(draft.activities) == 5
        assert len({activity.place_id for activity in draft.activities}) == 5
        assert sum("마라탕" in activity.matched_tags for activity in draft.activities) == 1
        assert (
            sum(
                activity.source_category in {"한식", "중식", "일식", "양식", "분식", "고깃집"}
                for activity in draft.activities
            )
            == 2
        )
        assert any("전시" in activity.matched_tags for activity in draft.activities)

    overlaps = [
        _place_jaccard(drafts[left], drafts[right])
        for left in range(3)
        for right in range(left + 1, 3)
    ]
    assert max(overlaps) <= 0.5


def test_algorithm_includes_activity_category_when_room_and_available():
    """식사 슬롯 외에 자리가 남고 후보 풀에 놀거리 카테고리가 있으면, 취향
    태그가 활동 카테고리를 가리키지 않아도(여기서는 순수 음식 태그만 줌) 최소
    한 곳은 액티비티/방탈출/보드게임카페/전시/공연장/영화관 중 하나가 들어가야
    한다 — 안 그러면 식사·카페류로만 채워지는 게 이 balancing 로직이 막으려는
    상황이다(2026-08-14, 사용자 관측: 일정이 먹거리 위주로 쏠림)."""
    conditions = _conditions().model_copy(
        update={
            "liked_tags": [
                PreferenceTag(
                    tag="마라탕",
                    verifiable=True,
                    is_meal=True,
                    preference_kind="food_menu",
                    priority=5,
                ),
            ],
        }
    )
    activity_categories = {"액티비티", "방탈출", "보드게임카페", "전시", "공연장", "영화관"}

    labeled = generate_algorithm_candidates("upstage", "unused", conditions, _places())

    assert labeled
    for _, draft in labeled:
        assert any(activity.source_category in activity_categories for activity in draft.activities)


def test_algorithm_meets_meal_slots_when_liked_tags_are_all_non_meal():
    """meal_tags가 비어도(좋아요 태그가 전부 non-meal) beam search가 필수 식사
    슬롯(점심+저녁 2곳)을 실제로 채워야 한다. 식사 태그가 하나도 없으면 두 식사
    슬롯 다 "자연 경쟁"으로 채워지는데, 활동 카테고리 점수 가산이 식사 카테고리의
    새-카테고리 보너스와 맞먹어서 beam이 식사 대신 활동 장소로 자리를 채우다가
    최종 meal_count 미달로 조합 전체가 드롭되는 사례가 실측됐다(2026-08-14,
    "서울 홍대" 재현: 좋아요=와플·방탈출, 둘 다 is_meal=False)."""
    conditions = _conditions().model_copy(
        update={
            "liked_tags": [
                PreferenceTag(
                    tag="전시",
                    verifiable=True,
                    is_meal=False,
                    preference_kind="place_type",
                    priority=3,
                ),
            ],
        }
    )
    meal_categories = {"한식", "중식", "일식", "양식", "분식", "고깃집"}

    labeled = generate_algorithm_candidates("upstage", "unused", conditions, _places())

    assert labeled
    for _, draft in labeled:
        meal_count = sum(
            activity.source_category in meal_categories for activity in draft.activities
        )
        assert meal_count >= 2, [a.source_category for a in draft.activities]


def test_ensure_place_ids_preserves_search_result_metadata():
    from app.services.naver_local_search import PlaceSearchResult

    places = PlaceSearchResult(
        [{"title": "전시관", "roadAddress": "서울 강남구 테스트로 1"}],
        {"candidate_count": 1, "groups": {"liked": [], "disliked": [], "categories": []}},
    )

    result = ensure_place_ids(places)

    assert result is places
    assert result[0]["place_id"]
    assert result.search_groups["candidate_count"] == 1


def test_multiple_required_places_from_same_tag_are_allowed_without_third_duplicate():
    places = _places()
    required = tuple(place["place_id"] for place in places[:2])

    labeled = generate_algorithm_candidates(
        "upstage",
        "unused",
        _conditions(),
        places,
        required,
        ("마라탕",),
    )

    assert labeled
    for _, draft in labeled:
        ids = {activity.place_id for activity in draft.activities}
        assert set(required).issubset(ids)
        assert sum("마라탕" in activity.matched_tags for activity in draft.activities) == 2


def test_replacement_keeps_remaining_places_and_adds_exactly_one():
    places = _places()
    fixed = tuple(place["place_id"] for place in places[3:7])

    labeled = generate_algorithm_candidates(
        "upstage",
        "unused",
        _conditions().model_copy(update={"liked_tags": []}),
        places,
        fixed_place_ids=fixed,
        candidate_limit=1,
        target_count=5,
    )

    assert len(labeled) == 1
    result_ids = {activity.place_id for activity in labeled[0][1].activities}
    assert set(fixed).issubset(result_ids)
    assert len(result_ids - set(fixed)) == 1


def test_verifiable_disliked_place_is_filtered_but_required_place_wins():
    places = _places()
    required_id = places[15]["place_id"]
    conditions = _conditions().model_copy(
        update={
            "disliked_tags": [
                PreferenceTag(
                    tag="공연",
                    verifiable=True,
                    preference_kind="place_type",
                )
            ]
        }
    )

    normal = generate_algorithm_candidates("upstage", "unused", conditions, places)
    assert normal
    assert all(
        all(activity.source_category != "공연장" for activity in draft.activities)
        for _, draft in normal
    )

    required = generate_algorithm_candidates(
        "upstage",
        "unused",
        conditions.model_copy(update={"liked_tags": []}),
        places,
        fixed_place_ids=(required_id,),
        candidate_limit=1,
    )
    assert required
    assert required_id in {activity.place_id for activity in required[0][1].activities}

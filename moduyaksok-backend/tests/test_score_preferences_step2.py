from datetime import datetime

from app.pipeline.schemas import NormalizedConditions, PreferenceTag
from app.pipeline.score_preferences_step2 import (
    PlacePreferenceScore,
    PlacePreferenceScoreBatch,
    score_soft_preferences,
    select_places_for_soft_scoring,
)


def _conditions(*, soft: bool = True) -> NormalizedConditions:
    return NormalizedConditions(
        purpose="date",
        headcount=2,
        time_range=(datetime(2026, 8, 15, 14), datetime(2026, 8, 15, 18)),
        region="서울 강남",
        liked_tags=[PreferenceTag(tag="조용한 곳", verifiable=False, preference_kind="atmosphere")]
        if soft
        else [PreferenceTag(tag="전시", verifiable=True, preference_kind="place_type")],
        disliked_tags=[],
        budget_per_person=50_000,
    )


def test_scores_all_places_in_one_structured_call_and_ignores_unknown_ids(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return PlacePreferenceScoreBatch(
            scores=[
                PlacePreferenceScore(place_id="p1", liked_score=0.8, disliked_score=0.1),
                PlacePreferenceScore(
                    place_id="unknown",
                    liked_score=1,
                    disliked_score=0,
                    matched_liked_preferences=["모델이 지어낸 조건"],
                ),
            ]
        )

    monkeypatch.setattr("app.pipeline.score_preferences_step2.call_structured", fake_call)
    result = score_soft_preferences(
        "upstage",
        "unused",
        _conditions(),
        [
            {"place_id": "p1", "title": "작은 전시관"},
            {"place_id": "p2", "title": "대형 쇼핑몰"},
        ],
    )

    assert len(calls) == 1
    assert set(result) == {"p1"}
    assert "p1" in calls[0]["user"] and "p2" in calls[0]["user"]


def test_skips_ai_call_without_soft_preferences(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.score_preferences_step2.call_structured",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("호출되면 안 됨")),
    )

    assert score_soft_preferences("upstage", "unused", _conditions(soft=False), []) == {}


def test_soft_scoring_failure_does_not_block_schedule_generation(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.score_preferences_step2.call_structured",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError),
    )

    assert score_soft_preferences("upstage", "unused", _conditions(), [{"place_id": "p1"}]) == {}


def test_soft_scoring_keeps_category_diversity_and_caps_prompt_at_24():
    places = [
        {
            "place_id": f"{category}-{index}",
            "title": f"{category} 장소 {index}",
            "source_category": category,
        }
        for category in ("카페", "전시", "한식", "액티비티", "영화관", "양식", "공연장", "술집")
        for index in range(5)
    ]

    selected = select_places_for_soft_scoring(places, prioritized_place_ids=("카페-4",))

    assert len(selected) == 16  # 8개 카테고리 × 최대 2곳
    assert "카페-4" in {place["place_id"] for place in selected}
    assert {place["source_category"] for place in selected} == {
        "카페",
        "전시",
        "한식",
        "액티비티",
        "영화관",
        "양식",
        "공연장",
        "술집",
    }


def test_soft_scoring_sends_only_reduced_place_list_to_single_llm_call(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return PlacePreferenceScoreBatch(scores=[])

    monkeypatch.setattr("app.pipeline.score_preferences_step2.call_structured", fake_call)
    places = [
        {
            "place_id": f"p{index}",
            "title": f"장소 {index}",
            "source_category": f"카테고리 {index % 15}",
        }
        for index in range(60)
    ]

    score_soft_preferences("upstage", "unused", _conditions(), places)

    assert captured["user"].count("\n- ") == 24

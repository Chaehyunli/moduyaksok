# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : generate_candidates() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 만드는지가 아니라 우리 fan-out/조립/부분실패
#              처리 로직을 검증한다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, region: str -> regions: list[str] 변경 반영. 지역 2개를 넣어 프롬프트에
#             둘 다 들어가는지 검증하는 assert 추가.
# 2026-08-11(2차), regions: list[str] -> region: str로 다시 축소되면서 위 테스트를
#             단일 지역 검증으로 되돌림. _MEAL_CATEGORIES 세분화에 맞춰 "[맛집]"
#             표시 관련 테스트도 세분화된 카테고리("한식" 등) 기준으로 변경.
# 2026-08-09, Step2를 "장소 선택"(LLM)과 "시간 배정"(결정론적 계산)으로 분리 —
#             call_structured는 이제 CandidateSelectionDraft(시간 없음)를 반환하고,
#             _schedule_places()가 시간을 채운다. _fake_draft를 CandidateSelectionDraft
#             기준으로 바꾸고, _schedule_places() 전용 테스트 추가.
# 2026-08-10, _schedule_places()가 place_candidates 좌표로 활동 사이 버퍼를
#             구간마다 다르게 잡도록 바뀌어서(travel_estimate.py), 좌표 부착·가변
#             버퍼 테스트 추가. place_candidates 생략 시 기존 고정 버퍼로 폴백하는
#             동작은 위 테스트들이 그대로 검증(하위호환).
# 2026-08-10, generate_candidates_with_perspectives()/generate_single_candidate()
#             테스트 추가 — Step3 재시도 오케스트레이터(orchestrate.py)가 쓸
#             "관점 라벨 유지"·"관점 하나만 재생성" 기능 검증.
# ------------------------------------------------------------------
from datetime import datetime, time

import pytest

from app.pipeline.generate_step2 import (
    PERSPECTIVES,
    _build_candidate_plans,
    _build_system_prompt,
    _build_user_prompt,
    _dedupe_places,
    _format_place_candidates,
    _meal_slot_instruction,
    _required_meal_windows,
    _schedule_places,
    _tag_bundles_by_perspective,
    generate_candidates,
    generate_candidates_with_perspectives,
    generate_single_candidate,
)
from app.pipeline.schemas import (
    CandidateDraft,
    CandidateSelectionDraft,
    NormalizedConditions,
    PlaceSelectionDraft,
    PreferenceTag,
)

_CONDITIONS = NormalizedConditions(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    region="서울 잠실",
    liked_tags=[PreferenceTag(tag="콩국수", verifiable=True, is_meal=True)],
    disliked_tags=[
        PreferenceTag(tag="해산물", verifiable=True),
        PreferenceTag(tag="사람 많은 곳", verifiable=False),
    ],
    budget_per_person=50000,
)

_PLACE_CANDIDATES = [
    {
        "title": "잠실장어와 한우",
        "category": "한식",
        "roadAddress": "서울 송파구 백제고분로7길",
        "source_category": "한식",
        "matched_tags": ["콩국수"],
        "mapx": "1270000000",
        "mapy": "375000000",
    },
    {
        "title": "OO카페",
        "category": "카페",
        "address": "서울 송파구 잠실동",
        "source_category": "카페",
        "mapx": "1270001000",
        "mapy": "375000100",
    },
    {
        "title": "석촌 파스타",
        "category": "양식",
        "roadAddress": "서울 송파구 잠실동",
        "source_category": "양식",
        "mapx": "1270002000",
        "mapy": "375000200",
    },
]


def _fake_draft(perspective: str) -> CandidateSelectionDraft:
    return CandidateSelectionDraft(
        title=f"{perspective} 초안",
        places=[
            PlaceSelectionDraft(
                name="잠실장어와 한우",
                category="한식",
                price_range_per_person=(20000, 30000),
            )
        ],
        rationale=f"{perspective} 반영",
    )


async def test_generate_candidates_returns_three_drafts_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.generate_step2.call_structured",
        lambda **kwargs: _fake_draft(kwargs["system"]),
    )

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    assert len(drafts) == 3
    assert all(isinstance(d, CandidateDraft) for d in drafts)


async def test_generate_candidates_passes_correct_provider_api_key_model(monkeypatch):
    captured: list[dict] = []

    def fake_call_structured(**kwargs):
        captured.append(kwargs)
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    await generate_candidates("upstage", "up-fake", _CONDITIONS, _PLACE_CANDIDATES)

    assert len(captured) == 3
    for call in captured:
        assert call["provider"] == "upstage"
        assert call["api_key"] == "up-fake"
        assert call["model"]  # get_model()이 뭘 반환하든 빈 값만 아니면 됨
        assert call["schema"] is CandidateSelectionDraft


async def test_generate_candidates_calls_each_perspective_exactly_once(monkeypatch):
    seen_perspectives: list[str] = []

    def fake_call_structured(**kwargs):
        for label, _instruction in PERSPECTIVES:
            if label in kwargs["system"]:
                seen_perspectives.append(label)
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    assert sorted(seen_perspectives) == sorted(label for label, _instruction in PERSPECTIVES)


async def test_generate_candidates_partial_failure_returns_remaining(monkeypatch):
    call_count = 0

    def fake_call_structured(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("이 관점 호출 실패")
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    assert len(drafts) == 2


async def test_generate_candidates_all_failures_raises_runtime_error(monkeypatch):
    def fake_call_structured(**kwargs):
        raise RuntimeError("전부 실패")

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    with pytest.raises(RuntimeError):
        await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)


async def test_generate_candidates_corrects_category_mismatched_from_place_candidates(monkeypatch):
    """Solar가 place의 category를 다른 장소 것과 뒤섞어 반환하는 결함이 실측으로
    확인됨(golden_step2.py 여러 케이스에서 재현) — LLM이 되돌려준 category는 못 믿고,
    place_candidates의 title이 일치하는 항목에서 category를 다시 가져와 덮어쓴다.
    """

    def fake_call_structured(**kwargs):
        return CandidateSelectionDraft(
            title="초안",
            places=[
                PlaceSelectionDraft(
                    # place_candidates의 실제 category("한식")와 다른 값을 일부러 넣음
                    name="잠실장어와 한우",
                    category="공원,자연>한강공원",
                    price_range_per_person=(20000, 30000),
                )
            ],
            rationale="반영",
        )

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    for draft in drafts:
        assert draft.activities[0].category == "한식"


async def test_generate_candidates_leaves_category_unchanged_when_name_not_in_place_candidates(
    monkeypatch,
):
    """place_candidates에 없는 이름(환각)이면 고칠 근거가 없으니 category를 그대로
    둔다 — 환각 자체를 잡아내는 건 GEval 채점의 몫이고, 이 보정은 "이름은 맞는데
    category만 틀린" 경우만 고친다."""

    def fake_call_structured(**kwargs):
        return CandidateSelectionDraft(
            title="초안",
            places=[
                PlaceSelectionDraft(
                    name="place_candidates에 없는 장소",
                    category="아무 카테고리",
                    price_range_per_person=(20000, 30000),
                )
            ],
            rationale="반영",
        )

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    for draft in drafts:
        assert draft.activities[0].category == "아무 카테고리"


async def test_generate_candidates_dedupes_repeated_place_in_same_selection(monkeypatch):
    """LLM이 같은 장소를 시간 채우려고 두 번 선택해도(golden_step2.py
    no_hallucinated_places_small_candidate_list에서 실측 재현) 최종 활동에는
    한 번만 남아야 한다(2026-08-12(2차))."""

    def fake_call_structured(**kwargs):
        return CandidateSelectionDraft(
            title="초안",
            places=[
                PlaceSelectionDraft(
                    name="잠실장어와 한우", category="한식", price_range_per_person=(20000, 30000)
                ),
                PlaceSelectionDraft(
                    name="OO카페", category="카페", price_range_per_person=(5000, 8000)
                ),
                PlaceSelectionDraft(
                    name="잠실장어와 한우", category="한식", price_range_per_person=(20000, 30000)
                ),
            ],
            rationale="반영",
        )

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    for draft in drafts:
        names = [a.name for a in draft.activities]
        assert names.count("잠실장어와 한우") == 1
        assert names == ["잠실장어와 한우", "OO카페"]


def test_dedupe_places_keeps_first_occurrence_only():
    places = [_place("가게1"), _place("가게2"), _place("가게1")]

    result = _dedupe_places(places)

    assert [p.name for p in result] == ["가게1", "가게2"]


def test_dedupe_places_no_duplicates_returns_unchanged():
    places = [_place("가게1"), _place("가게2")]

    assert _dedupe_places(places) == places


def test_build_user_prompt_injects_place_candidates_and_conditions():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "잠실장어와 한우" in prompt
    assert "OO카페" in prompt
    assert "서울 잠실" in prompt
    assert "50000" in prompt


def test_build_user_prompt_formats_tags_with_verifiable_and_meal_flags():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "콩국수(verifiable=True, is_meal=True)" in prompt
    assert "해산물(verifiable=True, is_meal=False)" in prompt
    assert "사람 많은 곳(verifiable=False, is_meal=False)" in prompt


def test_build_user_prompt_includes_fixed_tag_anchors():
    prompt = _build_user_prompt(
        _CONDITIONS,
        _PLACE_CANDIDATES,
        required_tag_anchors=(("콩국수", "잠실장어와 한우"),),
    )

    assert "고정 장소 앵커" in prompt
    assert "콩국수 → 잠실장어와 한우" in prompt


def test_build_user_prompt_handles_empty_place_candidates():
    prompt = _build_user_prompt(_CONDITIONS, [])

    assert "없음" in prompt


# ── purpose 가이던스 (2026-08-11) ────────────────────────────────────────


def test_build_user_prompt_injects_purpose_guidance_for_date():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "데이트 목적이다" in prompt


def test_build_user_prompt_injects_purpose_guidance_for_family():
    conditions = _CONDITIONS.model_copy(update={"purpose": "family"})

    prompt = _build_user_prompt(conditions, _PLACE_CANDIDATES)

    assert "가족 모임 목적이다" in prompt


def test_build_user_prompt_other_purpose_has_no_extra_guidance():
    conditions = _CONDITIONS.model_copy(update={"purpose": "other"})

    prompt = _build_user_prompt(conditions, _PLACE_CANDIDATES)

    assert "목적: other\n" in prompt


# ── 식사 슬롯 (2026-08-11) ──────────────────────────────────────────────


def test_required_meal_windows_includes_both_when_range_spans_both():
    windows = _required_meal_windows((datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)))
    assert len(windows) == 2


def test_required_meal_windows_lunch_only():
    windows = _required_meal_windows((datetime(2026, 8, 15, 11, 0), datetime(2026, 8, 15, 14, 0)))
    assert windows == [(time(12, 0), time(13, 0))]


def test_required_meal_windows_empty_for_narrow_afternoon_range():
    windows = _required_meal_windows((datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0)))
    assert windows == []


def test_meal_slot_instruction_empty_when_no_windows_required():
    instruction = _meal_slot_instruction(
        (datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0))
    )
    assert instruction == ""


def test_meal_slot_instruction_mentions_lunch_and_dinner_and_meal_category_bracket():
    instruction = _meal_slot_instruction(
        (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))
    )
    assert "점심" in instruction
    assert "저녁" in instruction
    assert "[한식]" in instruction  # _MEAL_CATEGORIES 중 하나가 대괄호로 표시됨


def test_build_user_prompt_injects_meal_slot_instruction():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)  # 10:00~21:00, 둘 다 필요

    assert "점심" in prompt
    assert "저녁" in prompt


def test_build_user_prompt_omits_meal_slot_instruction_when_not_needed():
    conditions = _CONDITIONS.model_copy(
        update={"time_range": (datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0))}
    )

    prompt = _build_user_prompt(conditions, _PLACE_CANDIDATES)

    assert "식사가 되는 카테고리" not in prompt


def test_required_liked_tag_filters_optional_places_of_same_tag_from_plans():
    places = [
        {
            "place_id": "required",
            "title": "필수 중식당",
            "category": "중식",
            "source_category": "중식",
            "matched_tags": ["콩국수"],
            "mapx": "1270000000",
            "mapy": "375000000",
        },
        {
            "place_id": "duplicate",
            "title": "일반 콩국수집",
            "category": "한식",
            "source_category": "한식",
            "matched_tags": ["콩국수"],
            "mapx": "1270000100",
            "mapy": "375000100",
        },
        {
            "place_id": "dinner",
            "title": "저녁 식당",
            "category": "한식",
            "source_category": "한식",
            "mapx": "1270000200",
            "mapy": "375000200",
        },
        {
            "place_id": "activity",
            "title": "전시장",
            "category": "전시",
            "source_category": "전시",
            "mapx": "1270000300",
            "mapy": "375000300",
        },
    ]

    plans = _build_candidate_plans(
        _CONDITIONS,
        places,
        required_place_ids=("required",),
        precovered_liked_tags=("콩국수",),
    )

    assert plans
    assert all("필수 중식당" in {p["title"] for p in plan.place_candidates} for plan in plans)
    assert all("일반 콩국수집" not in {p["title"] for p in plan.place_candidates} for plan in plans)


def test_format_place_candidates_shows_source_category_bracket():
    formatted = _format_place_candidates(
        [{"title": "잠실집", "category": "한식", "source_category": "한식"}]
    )
    assert "[한식]" in formatted


def test_format_place_candidates_no_bracket_when_source_category_missing():
    formatted = _format_place_candidates([{"title": "잠실집", "category": "한식"}])
    assert "[" not in formatted


def test_build_system_prompt_states_hard_constraint_for_verifiable_true():
    prompt = _build_system_prompt(PERSPECTIVES[0])

    assert "verifiable=true" in prompt
    assert "반드시 배제" in prompt


def test_build_system_prompt_states_soft_signal_for_verifiable_false():
    prompt = _build_system_prompt(PERSPECTIVES[0])

    assert "verifiable=false" in prompt
    assert "보장한다고 말하지 마라" in prompt


def test_build_system_prompt_limits_same_tag_to_one_place_per_candidate():
    prompt = _build_system_prompt(PERSPECTIVES[0])

    assert "최대 1곳" in prompt


def test_build_system_prompt_includes_perspective_text():
    label, instruction = PERSPECTIVES[1]
    prompt = _build_system_prompt(PERSPECTIVES[1])

    assert label in prompt
    assert instruction in prompt


# ── _schedule_places() ──────────────────────────────────────────────────────

_WINDOW_10_TO_21 = (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))


def _place(name: str) -> PlaceSelectionDraft:
    return PlaceSelectionDraft(name=name, category="카테고리", price_range_per_person=(1000, 2000))


def test_schedule_places_returns_empty_list_for_no_places():
    assert _schedule_places([], _WINDOW_10_TO_21) == []


def test_schedule_places_first_activity_starts_at_window_start():
    activities = _schedule_places([_place("A")], _WINDOW_10_TO_21)

    assert activities[0].start_time == "10:00"


def test_schedule_places_preserves_name_category_and_price():
    place = PlaceSelectionDraft(name="A", category="한식", price_range_per_person=(5000, 8000))

    activities = _schedule_places([place], _WINDOW_10_TO_21)

    assert activities[0].name == "A"
    assert activities[0].category == "한식"
    assert activities[0].price_range_per_person == (5000, 8000)


def test_schedule_places_never_overlaps():
    places = [_place("A"), _place("B"), _place("C"), _place("D")]

    activities = _schedule_places(places, _WINDOW_10_TO_21)

    for earlier, later in zip(activities, activities[1:], strict=False):
        earlier_end = datetime.strptime(earlier.end_time, "%H:%M")
        later_start = datetime.strptime(later.start_time, "%H:%M")
        assert earlier_end <= later_start


def test_schedule_places_stays_within_window_for_reasonable_place_count():
    places = [_place(f"장소{i}") for i in range(4)]

    activities = _schedule_places(places, _WINDOW_10_TO_21)

    window_end = datetime.strptime("21:00", "%H:%M")
    assert datetime.strptime(activities[-1].end_time, "%H:%M") <= window_end


def test_schedule_places_preserves_visit_order():
    places = [_place("첫번째"), _place("두번째"), _place("세번째")]

    activities = _schedule_places(places, _WINDOW_10_TO_21)

    assert [a.name for a in activities] == ["첫번째", "두번째", "세번째"]


def test_schedule_places_caps_duration_for_few_places_in_wide_window():
    # 11시간 창에 활동 1개 — 활동 하나가 11시간짜리가 되면 안 되고 상한(90분) 이내여야 함
    activities = _schedule_places([_place("A")], _WINDOW_10_TO_21)

    start = datetime.strptime(activities[0].start_time, "%H:%M")
    end = datetime.strptime(activities[0].end_time, "%H:%M")
    assert (end - start).total_seconds() / 60 <= 90


def test_schedule_places_floors_duration_for_many_places_in_narrow_window():
    narrow_window = (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 11, 0))
    places = [_place(f"장소{i}") for i in range(10)]

    activities = _schedule_places(places, narrow_window)

    start = datetime.strptime(activities[0].start_time, "%H:%M")
    end = datetime.strptime(activities[0].end_time, "%H:%M")
    assert (end - start).total_seconds() / 60 >= 30


# ── _schedule_places() 좌표 기반 버퍼 (2026-08-10) ──────────────────────────

# 강남역/서울시청 실측 좌표(mapx/mapy 실측 검증에 썼던 것과 동일) — mapx=경도×1e7,
# mapy=위도×1e7.
_GANGNAM_CANDIDATE = {"title": "강남역", "mapx": "1270276210", "mapy": "374979420"}
_NEARBY_CANDIDATE = {"title": "근처장소", "mapx": "1270280000", "mapy": "374985000"}
_CITY_HALL_CANDIDATE = {"title": "서울시청", "mapx": "1269765000", "mapy": "375648000"}


def test_schedule_places_attaches_coordinates_from_place_candidates():
    places = [_place("강남역")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [_GANGNAM_CANDIDATE])

    assert activities[0].address == ""  # 이 픽스처엔 address/roadAddress가 없음
    assert activities[0].lat == pytest.approx(37.497942)
    assert activities[0].lng == pytest.approx(127.027621)


def test_schedule_places_leaves_coordinates_empty_when_not_in_place_candidates():
    places = [_place("place_candidates에 없는 장소")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [_GANGNAM_CANDIDATE])

    assert activities[0].lat is None
    assert activities[0].lng is None


def test_schedule_places_uses_smaller_buffer_for_closer_places():
    close_places = [_place("강남역"), _place("근처장소")]
    far_places = [_place("강남역"), _place("서울시청")]
    candidates = [_GANGNAM_CANDIDATE, _NEARBY_CANDIDATE, _CITY_HALL_CANDIDATE]

    close_activities = _schedule_places(close_places, _WINDOW_10_TO_21, candidates)
    far_activities = _schedule_places(far_places, _WINDOW_10_TO_21, candidates)

    close_gap = datetime.strptime(close_activities[1].start_time, "%H:%M") - datetime.strptime(
        close_activities[0].end_time, "%H:%M"
    )
    far_gap = datetime.strptime(far_activities[1].start_time, "%H:%M") - datetime.strptime(
        far_activities[0].end_time, "%H:%M"
    )
    assert close_gap < far_gap


# ── _schedule_places() matched_tag 부착 (2026-08-11) ────────────────────────


def test_schedule_places_attaches_matched_tag_from_place_candidates():
    waffle_place = {**_GANGNAM_CANDIDATE, "matched_tag": "와플"}
    places = [_place("강남역")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [waffle_place])

    assert activities[0].matched_tag == "와플"


def test_schedule_places_matched_tag_is_none_when_not_tag_matched():
    places = [_place("강남역")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [_GANGNAM_CANDIDATE])

    assert activities[0].matched_tag is None


# ── _schedule_places() source_category 부착 (2026-08-11) ────────────────────


def test_schedule_places_attaches_source_category_from_place_candidates():
    place = {**_GANGNAM_CANDIDATE, "source_category": "맛집"}
    places = [_place("강남역")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [place])

    assert activities[0].source_category == "맛집"


def test_schedule_places_source_category_is_none_when_not_set():
    places = [_place("강남역")]

    activities = _schedule_places(places, _WINDOW_10_TO_21, [_GANGNAM_CANDIDATE])

    assert activities[0].source_category is None


def test_schedule_places_anchors_lunch_and_dinner_in_a_long_window():
    places = [_place("카페"), _place("점심식당"), _place("전시"), _place("저녁식당")]
    candidates = [
        {**_GANGNAM_CANDIDATE, "title": "카페", "source_category": "카페"},
        {**_NEARBY_CANDIDATE, "title": "점심식당", "source_category": "한식"},
        {**_NEARBY_CANDIDATE, "title": "전시", "source_category": "전시"},
        {**_GANGNAM_CANDIDATE, "title": "저녁식당", "source_category": "양식"},
    ]

    activities = _schedule_places(places, _WINDOW_10_TO_21, candidates)

    assert activities[1].start_time == "12:00"
    assert activities[3].start_time == "18:00"


# ── 클러스터·식사 태그 계획 (2026-08-12) ───────────────────────────────────


def test_candidate_plans_make_one_dinner_alternative_per_meal_tag():
    conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 21, 0)),
            "liked_tags": [
                PreferenceTag(tag="삼겹살", verifiable=True, is_meal=True),
                PreferenceTag(tag="콩국수", verifiable=True, is_meal=True),
                PreferenceTag(tag="스테이크", verifiable=True, is_meal=True),
                PreferenceTag(tag="와플", verifiable=True, is_meal=False),
            ],
        }
    )
    places = [
        {
            "title": tag,
            "source_category": "한식" if tag != "스테이크" else "양식",
            "matched_tags": [tag],
            "mapx": str(1270000000 + index * 1000),
            "mapy": str(375000000 + index * 1000),
        }
        for index, tag in enumerate(("삼겹살", "콩국수", "스테이크", "와플"))
    ]

    plans = _build_candidate_plans(conditions, places)

    assert {plan.required_meal_tags for plan in plans} == {
        ("삼겹살",),
        ("콩국수",),
        ("스테이크",),
    }
    assert all(plan.required_non_meal_tags == ("와플",) for plan in plans)
    assert all(plan.cluster_radius_meters == 1_000 for plan in plans)


def test_candidate_plans_assign_different_real_meal_anchors_to_each_option():
    conditions = _CONDITIONS.model_copy(
        update={
            "liked_tags": [
                PreferenceTag(tag="햄버거", verifiable=True, is_meal=True),
                PreferenceTag(tag="콩국수", verifiable=True, is_meal=True),
                PreferenceTag(tag="와플", verifiable=True, is_meal=False),
            ],
        }
    )
    places = [
        {
            "title": name,
            "source_category": category,
            "matched_tags": tags,
            "mapx": str(1270000000 + index * 1000),
            "mapy": str(375000000 + index * 1000),
        }
        for index, (name, category, tags) in enumerate(
            (
                ("버거1", "양식", ["햄버거"]),
                ("버거2", "양식", ["햄버거"]),
                ("버거3", "양식", ["햄버거"]),
                ("콩국수집", "한식", ["콩국수"]),
                ("와플집", "카페", ["와플"]),
            )
        )
    ]

    plans = _build_candidate_plans(conditions, places)

    assert len(plans) == 3
    assert {dict(plan.required_tag_anchors)["햄버거"] for plan in plans} == {
        "버거1",
        "버거2",
        "버거3",
    }
    assert all(dict(plan.required_tag_anchors)["콩국수"] == "콩국수집" for plan in plans)
    assert all(dict(plan.required_tag_anchors)["와플"] == "와플집" for plan in plans)


def test_candidate_plans_do_not_use_cafe_as_a_meal_tag_anchor():
    conditions = _CONDITIONS.model_copy(
        update={"liked_tags": [PreferenceTag(tag="햄버거", verifiable=True, is_meal=True)]}
    )
    places = [
        {
            "title": "햄버거 검색에 섞인 카페",
            "category": "카페,디저트>카페",
            "matched_tags": ["햄버거"],
            "mapx": "1270000000",
            "mapy": "375000000",
        },
        {
            "title": "실제 버거집",
            "category": "음식점>햄버거",
            "matched_tags": ["햄버거"],
            "mapx": "1270001000",
            "mapy": "375000100",
        },
        {
            "title": "일반 식당",
            "source_category": "한식",
            "mapx": "1270002000",
            "mapy": "375000200",
        },
    ]

    plans = _build_candidate_plans(conditions, places)

    assert plans
    assert all(dict(plan.required_tag_anchors)["햄버거"] == "실제 버거집" for plan in plans)


def test_tag_search_meal_results_without_source_category_form_distinct_anchors():
    conditions = _CONDITIONS.model_copy(
        update={"liked_tags": [PreferenceTag(tag="중식", verifiable=True, is_meal=True)]}
    )
    places = [
        {
            "title": f"중식당 {index}",
            "category": "음식점>중식",
            "matched_tags": ["중식"],
            "mapx": str(1270000000 + index * 1000),
            "mapy": str(375000000 + index * 1000),
        }
        for index in range(3)
    ]

    plans = _build_candidate_plans(conditions, places)

    assert len(plans) == 3
    assert {dict(plan.required_tag_anchors)["중식"] for plan in plans} == {
        "중식당 0",
        "중식당 1",
        "중식당 2",
    }


def test_required_meal_anchor_is_assigned_to_a_meal_window_before_generic_meal():
    places = [_place("일반식당"), _place("필수식당"), _place("카페"), _place("저녁식당")]
    candidates = [
        {**_GANGNAM_CANDIDATE, "title": "일반식당", "source_category": "한식"},
        {**_NEARBY_CANDIDATE, "title": "필수식당", "source_category": "중식"},
        {**_NEARBY_CANDIDATE, "title": "카페", "source_category": "카페"},
        {**_GANGNAM_CANDIDATE, "title": "저녁식당", "source_category": "양식"},
    ]

    activities = _schedule_places(
        places,
        _WINDOW_10_TO_21,
        candidates,
        meal_anchor_names=frozenset({"필수식당"}),
    )

    assert activities[1].start_time in {"12:00", "18:00"}
    assert {activities[0].start_time, activities[1].start_time} == {"12:00", "18:00"}


def test_candidate_plans_prefer_more_liked_tags_even_when_minimum_coverage_is_met():
    conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 21, 0)),
            "liked_tags": [
                PreferenceTag(tag="삼겹살", verifiable=True, is_meal=True),
                PreferenceTag(tag="와플", verifiable=True, is_meal=False),
            ],
        }
    )
    # 남북 약 1.3km: 1km 묶음은 최소 기준(식사 태그 1개)을 충족하지만,
    # 두 태그를 모두 담는 1.5km 계획이 더 높은 선호 점수로 우선 선택된다.
    places = [
        {
            "title": "삼겹살집",
            "source_category": "고깃집",
            "matched_tags": ["삼겹살"],
            "mapx": "1270000000",
            "mapy": "375000000",
        },
        {
            "title": "와플집",
            "source_category": "카페",
            "matched_tags": ["와플"],
            "mapx": "1270000000",
            "mapy": "375117000",
        },
    ]

    plans = _build_candidate_plans(conditions, places)

    assert plans
    assert any(plan.cluster_radius_meters == 1_500 for plan in plans)
    assert any(len(plan.required_tag_anchors) >= 2 for plan in plans)


def test_required_place_reclusters_around_selected_place_and_keeps_it_in_every_plan():
    conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0)),
            "liked_tags": [],
        }
    )
    places = [
        {
            "place_id": "must-cafe",
            "title": "선택한 카페",
            "source_category": "카페",
            "mapx": "1270000000",
            "mapy": "375000000",
        },
        {
            "place_id": "near-activity",
            "title": "가까운 전시",
            "source_category": "전시",
            "mapx": "1270001000",
            "mapy": "375000100",
        },
        {
            "place_id": "far-cafe",
            "title": "먼 카페",
            "source_category": "카페",
            "mapx": "1270300000",
            "mapy": "375000000",
        },
    ]

    plans = _build_candidate_plans(conditions, places, ("must-cafe",))

    assert plans
    assert all(plan.required_place_ids == ("must-cafe",) for plan in plans)
    assert all(
        "must-cafe" in {place["place_id"] for place in plan.place_candidates} for plan in plans
    )
    assert all(
        "far-cafe" not in {place["place_id"] for place in plan.place_candidates} for plan in plans
    )


def test_distant_required_places_bypass_cluster_radius_but_optional_places_stay_local():
    conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0)),
            "liked_tags": [],
        }
    )
    places = [
        {
            "place_id": "must-east",
            "title": "동쪽 필수 장소",
            "source_category": "전시",
            "mapx": "1270000000",
            "mapy": "375000000",
        },
        {
            "place_id": "must-west",
            "title": "서쪽 필수 장소",
            "source_category": "카페",
            # 첫 필수 장소에서 약 4.4km — 최대 2.5km 반경 밖이다.
            "mapx": "1269500000",
            "mapy": "375000000",
        },
        {
            "place_id": "near-east",
            "title": "동쪽 주변 장소",
            "source_category": "액티비티",
            "mapx": "1270001000",
            "mapy": "375000100",
        },
    ]

    plans = _build_candidate_plans(conditions, places, ("must-east", "must-west"))

    assert plans
    assert all(
        {"must-east", "must-west"}.issubset({place["place_id"] for place in plan.place_candidates})
        for plan in plans
    )


# ── _tag_bundles_by_perspective() (2026-08-11) ──────────────────────────────


def test_tag_bundles_returns_copies_of_shared_list_when_no_tag_matches():
    place_candidates = [{"title": "카페1", "category": "카페"}]

    bundles = _tag_bundles_by_perspective(place_candidates, 3)

    assert bundles == [place_candidates, place_candidates, place_candidates]


def test_tag_bundles_excludes_unlocated_place_when_coordinates_exist():
    unlocated = {"title": "좌표없는카페", "category": "카페"}
    located = [
        {"title": f"와플{i}", "matched_tag": "와플", "mapx": "1270000000", "mapy": "375000000"}
        for i in range(3)
    ]

    bundles = _tag_bundles_by_perspective([unlocated, *located], 3)

    for bundle in bundles:
        assert unlocated not in bundle


def test_tag_bundles_reuses_one_compact_pool_when_all_places_are_nearby():
    waffle = [
        {"title": f"와플{i}", "matched_tag": "와플", "mapx": "1270000000", "mapy": "375000000"}
        for i in range(3)
    ]

    bundles = _tag_bundles_by_perspective(waffle, 3)

    assert all({p["title"] for p in bundle} == {"와플0", "와플1", "와플2"} for bundle in bundles)


def test_tag_bundles_excludes_places_outside_1500m_radius():
    # 시드와 가까운 카페는 약 1.1km, 동쪽 액티비티는 약 1.8km라 같은 후보군에
    # 들어가면 안 된다. 시드 묶음은 식사·카페 두 카테고리를 가져 점수도 가장 높다.
    seed = {
        "title": "중심식당",
        "source_category": "한식",
        "mapx": "1270000000",
        "mapy": "375000000",
    }
    nearby = {
        "title": "가까운카페",
        "source_category": "카페",
        "mapx": "1270000000",
        "mapy": "375100000",
    }
    outside = {
        "title": "먼액티비티",
        "source_category": "액티비티",
        "mapx": "1270200000",
        "mapy": "375000000",
    }

    bundles = _tag_bundles_by_perspective([seed, nearby, outside], 1)

    assert {place["title"] for place in bundles[0]} == {"중심식당", "가까운카페"}


def test_tag_bundles_reuses_a_match_when_fewer_than_perspectives():
    waffle = [{"title": "와플1", "matched_tag": "와플", "mapx": "1270000000", "mapy": "375000000"}]

    bundles = _tag_bundles_by_perspective(waffle, 3)

    for bundle in bundles:
        assert bundle[0]["title"] == "와플1"  # 매칭이 1곳뿐이면 다 같은 곳을 볼 수밖에 없음


def test_tag_bundles_pairs_multiple_tags_by_proximity():
    # 와플1/파스타1은 서로 가깝고(강남), 와플2/파스타2도 서로 가깝다(홍대) —
    # 관점0은 강남 조합, 관점1은 홍대 조합을 봐야 한다(멀리 떨어진 조합이 섞이면 안 됨).
    waffle1 = {
        "title": "강남와플",
        "matched_tag": "와플",
        "mapx": "1270000000",
        "mapy": "375000000",
    }
    waffle2 = {
        "title": "홍대와플",
        "matched_tag": "와플",
        "mapx": "1269000000",
        "mapy": "378000000",
    }
    pasta1 = {
        "title": "강남파스타",
        "matched_tag": "파스타",
        "mapx": "1270010000",
        "mapy": "375010000",
    }
    pasta2 = {
        "title": "홍대파스타",
        "matched_tag": "파스타",
        "mapx": "1269010000",
        "mapy": "378010000",
    }

    bundles = _tag_bundles_by_perspective([waffle1, waffle2, pasta1, pasta2], 2)

    for bundle in bundles:
        titles = {p["title"] for p in bundle}
        assert titles == {"강남와플", "강남파스타"} or titles == {"홍대와플", "홍대파스타"}


# ── generate_candidates_with_perspectives() / generate_single_candidate() ──


async def test_generate_candidates_with_perspectives_labels_match_perspectives(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.generate_step2.call_structured",
        lambda **kwargs: _fake_draft(kwargs["system"]),
    )

    labeled = await generate_candidates_with_perspectives(
        "anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES
    )

    assert len(labeled) == 3
    assert sorted(label for label, _ in labeled) == sorted(label for label, _ in PERSPECTIVES)
    assert all(isinstance(draft, CandidateDraft) for _, draft in labeled)


async def test_generate_candidates_with_perspectives_drops_label_of_failed_perspective(
    monkeypatch,
):
    call_count = 0

    def fake_call_structured(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("이 관점 호출 실패")
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    labeled = await generate_candidates_with_perspectives(
        "anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES
    )

    assert len(labeled) == 2


async def test_generate_candidates_wrapper_still_returns_plain_drafts(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.generate_step2.call_structured",
        lambda **kwargs: _fake_draft(kwargs["system"]),
    )

    drafts = await generate_candidates("anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES)

    assert len(drafts) == 3
    assert all(isinstance(d, CandidateDraft) for d in drafts)


def test_generate_single_candidate_uses_matching_perspective_prompt(monkeypatch):
    captured = {}

    def fake_call_structured(**kwargs):
        captured["system"] = kwargs["system"]
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    label, instruction = PERSPECTIVES[1]
    draft = generate_single_candidate(
        "anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES, label
    )

    assert isinstance(draft, CandidateDraft)
    assert label in captured["system"]
    assert instruction in captured["system"]


def test_generate_single_candidate_raises_for_unknown_perspective_label():
    with pytest.raises(ValueError):
        generate_single_candidate(
            "anthropic", "sk-ant-fake", _CONDITIONS, _PLACE_CANDIDATES, "존재하지 않는 관점"
        )


# ── 관점별로 다른 place_candidates를 보는지 (2026-08-11) ─────────────────────

_WAFFLE_MATCHES = [
    {
        "title": f"와플{i}",
        "category": "카페,디저트>와플",
        "matched_tag": "와플",
        "mapx": "1270000000",
        "mapy": "375000000",
    }
    for i in range(3)
]


async def test_generate_candidates_gives_each_perspective_a_different_tag_match(monkeypatch):
    captured_users: list[str] = []

    def fake_call_structured(**kwargs):
        captured_users.append(kwargs["user"])
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    nearby = [
        {
            "title": f"강남와플{i}",
            "category": "카페",
            "matched_tag": "와플",
            "mapx": str(1270000000 + i * 10000),
            "mapy": str(375000000 + i * 10000),
        }
        for i in range(2)
    ]
    distant = [
        {
            "title": f"홍대와플{i}",
            "category": "카페",
            "matched_tag": "와플",
            "mapx": str(1269000000 + i * 10000),
            "mapy": str(378000000 + i * 10000),
        }
        for i in range(2)
    ]

    waffle_conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 17, 0)),
            "liked_tags": [PreferenceTag(tag="와플", verifiable=True, is_meal=False)],
        }
    )
    await generate_candidates("anthropic", "sk-ant-fake", waffle_conditions, [*nearby, *distant])

    assert len(captured_users) == 3
    # 한 프롬프트 안에 강남·홍대 후보가 섞이면 안 된다. 관점별 후보의 차이는
    # "서로 다른 태그 하나"보다 "실제로 이동 가능한 근거리 묶음"이 우선이다.
    assert all(not ("강남와플" in user and "홍대와플" in user) for user in captured_users)


def test_generate_single_candidate_reuses_same_partition_as_full_run(monkeypatch):
    captured: dict[str, str] = {}

    def fake_call_structured(**kwargs):
        captured["user"] = kwargs["user"]
        return _fake_draft(kwargs["system"])

    monkeypatch.setattr("app.pipeline.generate_step2.call_structured", fake_call_structured)

    waffle_conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 17, 0)),
            "liked_tags": [PreferenceTag(tag="와플", verifiable=True, is_meal=False)],
        }
    )
    label = PERSPECTIVES[1][0]
    index = 1
    generate_single_candidate("anthropic", "sk-ant-fake", waffle_conditions, _WAFFLE_MATCHES, label)

    expected_bundle = _tag_bundles_by_perspective(_WAFFLE_MATCHES, len(PERSPECTIVES))[index]
    expected_title = next(p["title"] for p in expected_bundle if p.get("matched_tag") == "와플")
    assert expected_title in captured["user"]

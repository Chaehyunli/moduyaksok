# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : generate_candidates() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 만드는지가 아니라 우리 fan-out/조립/부분실패
#              처리 로직을 검증한다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, region: str -> regions: list[str] 변경 반영. 지역 2개를 넣어 프롬프트에
#             둘 다 들어가는지 검증하는 assert 추가.
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
from datetime import datetime

import pytest

from app.pipeline.generate_step2 import (
    PERSPECTIVES,
    _build_system_prompt,
    _build_user_prompt,
    _schedule_places,
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
    regions=["서울 잠실", "서울 성수"],
    liked_tags=[PreferenceTag(tag="콩국수", verifiable=True)],
    disliked_tags=[
        PreferenceTag(tag="해산물", verifiable=True),
        PreferenceTag(tag="사람 많은 곳", verifiable=False),
    ],
    budget_per_person=50000,
)

_PLACE_CANDIDATES = [
    {"title": "잠실장어와 한우", "category": "한식", "roadAddress": "서울 송파구 백제고분로7길"},
    {"title": "OO카페", "category": "카페", "address": "서울 송파구 잠실동"},
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


def test_build_user_prompt_injects_place_candidates_and_conditions():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "잠실장어와 한우" in prompt
    assert "OO카페" in prompt
    assert "서울 잠실" in prompt
    assert "서울 성수" in prompt
    assert "50000" in prompt


def test_build_user_prompt_formats_tags_with_verifiable_flag():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "콩국수(verifiable=True)" in prompt
    assert "해산물(verifiable=True)" in prompt
    assert "사람 많은 곳(verifiable=False)" in prompt


def test_build_user_prompt_handles_empty_place_candidates():
    prompt = _build_user_prompt(_CONDITIONS, [])

    assert "없음" in prompt


def test_build_system_prompt_states_hard_constraint_for_verifiable_true():
    prompt = _build_system_prompt(PERSPECTIVES[0])

    assert "verifiable=true" in prompt
    assert "반드시 배제" in prompt


def test_build_system_prompt_states_soft_signal_for_verifiable_false():
    prompt = _build_system_prompt(PERSPECTIVES[0])

    assert "verifiable=false" in prompt
    assert "보장한다고 말하지 마라" in prompt


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

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : synthesize_and_validate() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 판단하는지가 아니라 규칙 기반 필터링/조립 로직을
#              검증한다.
# 작성일      : 2026-08-10
# ------------------------------------------------------------------
from datetime import datetime

from app.pipeline.schemas import (
    ActivityDraft,
    CandidateDraft,
    InfeasibleResponse,
    NormalizedConditions,
    PreferenceTag,
    ScheduleResponse,
)
from app.pipeline.synthesize_step3 import (
    _budget_overrun_ratio,
    _CandidateJudgment,
    _has_duplicate_place,
    _has_duplicate_tag_match,
    _has_excessive_travel,
    _has_hallucinated_activity,
    _has_missing_meal_slot,
    _has_missing_required_tags,
    _has_time_overlap,
    _JudgmentBatch,
    _required_meal_windows,
    _rule_based_filter,
    _similarity_score,
    _time_overrun_minutes,
    synthesize_and_validate,
)

_TIME_RANGE = (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))

# 점심(12~13시)/저녁(18~19시)이 안 낀 오후 시간대 — 식사 슬롯 하드룰(2026-08-11)과
# 무관한 기존 테스트들이 이 새 룰에 걸리지 않게 일부러 좁혔다. 식사 슬롯 자체를
# 테스트할 땐 _MEAL_CONDITIONS(아래, 점심·저녁 다 낀 _TIME_RANGE 재사용)를 쓴다.
_CONDITIONS = NormalizedConditions(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 14, 0), datetime(2026, 8, 15, 17, 0)),
    region="서울 잠실",
    liked_tags=[PreferenceTag(tag="콩국수", verifiable=True)],
    disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)],
    budget_per_person=50000,
)

_MEAL_CONDITIONS = _CONDITIONS.model_copy(update={"time_range": _TIME_RANGE})
# 점심만 필요한 좁은 창(11:00~14:00) — 점심/저녁을 각각 독립적으로 테스트하기 위함.
_LUNCH_ONLY_CONDITIONS = _CONDITIONS.model_copy(
    update={"time_range": (datetime(2026, 8, 15, 11, 0), datetime(2026, 8, 15, 14, 0))}
)


def _activity(
    name: str,
    category: str = "한식",
    start: str = "10:00",
    end: str = "11:00",
    price: tuple[int, int] = (10000, 15000),
    lat: float | None = 37.5,
    lng: float | None = 127.0,
    matched_tag: str | None = None,
    matched_tags: list[str] | None = None,
    source_category: str | None = None,
) -> ActivityDraft:
    return ActivityDraft(
        name=name,
        category=category,
        start_time=start,
        end_time=end,
        price_range_per_person=price,
        address="서울 송파구",
        lat=lat,
        lng=lng,
        matched_tag=matched_tag,
        matched_tags=matched_tags or [],
        source_category=source_category,
    )


def _candidate(title: str, activities: list[ActivityDraft], rationale: str = "r") -> CandidateDraft:
    return CandidateDraft(title=title, activities=activities, rationale=rationale)


# ── _similarity_score ────────────────────────────────────────────────────


def test_similarity_score_identical_activities_is_one():
    a = _candidate("A", [_activity("가게1"), _activity("가게2")])
    b = _candidate("B", [_activity("가게1"), _activity("가게2")])
    assert _similarity_score(a, b) == 1.0


def test_similarity_score_no_overlap_is_zero():
    a = _candidate("A", [_activity("가게1")])
    b = _candidate("B", [_activity("가게2")])
    assert _similarity_score(a, b) == 0.0


def test_similarity_score_partial_overlap():
    a = _candidate("A", [_activity("가게1"), _activity("가게2")])
    b = _candidate("B", [_activity("가게1"), _activity("가게3")])
    # 교집합 1개(가게1) / 합집합 3개 = 1/3
    assert abs(_similarity_score(a, b) - (1 / 3)) < 1e-9


# ── _has_hallucinated_activity / _has_time_overlap ──────────────────────


def test_has_hallucinated_activity_true_when_coordinates_missing():
    c = _candidate("A", [_activity("가게1", lat=None, lng=None)])
    assert _has_hallucinated_activity(c) is True


def test_has_hallucinated_activity_false_when_all_have_coordinates():
    c = _candidate("A", [_activity("가게1"), _activity("가게2")])
    assert _has_hallucinated_activity(c) is False


def test_has_time_overlap_true_when_activities_overlap():
    c = _candidate(
        "A",
        [
            _activity("가게1", start="10:00", end="11:30"),
            _activity("가게2", start="11:00", end="12:00"),
        ],
    )
    assert _has_time_overlap(c) is True


def test_has_time_overlap_false_when_sequential():
    c = _candidate(
        "A",
        [
            _activity("가게1", start="10:00", end="11:00"),
            _activity("가게2", start="11:30", end="12:00"),
        ],
    )
    assert _has_time_overlap(c) is False


# ── _has_duplicate_tag_match (2026-08-11, 태그 중복 반영 하드룰) ───────────


def test_has_duplicate_tag_match_true_when_same_tag_matched_twice():
    c = _candidate(
        "A",
        [
            _activity("가게1", matched_tag="와플"),
            _activity("가게2", matched_tag="와플"),
        ],
    )
    assert _has_duplicate_tag_match(c) is True


def test_has_duplicate_tag_match_false_when_different_tags():
    c = _candidate(
        "A",
        [
            _activity("가게1", matched_tag="와플"),
            _activity("가게2", matched_tag="파스타"),
        ],
    )
    assert _has_duplicate_tag_match(c) is False


def test_has_duplicate_tag_match_false_when_no_tags_matched():
    c = _candidate("A", [_activity("가게1"), _activity("가게2")])
    assert _has_duplicate_tag_match(c) is False


def test_has_duplicate_tag_match_uses_all_matched_tags():
    c = _candidate(
        "A",
        [
            _activity("가게1", matched_tags=["스시", "초밥"]),
            _activity("가게2", matched_tags=["스시"]),
        ],
    )
    assert _has_duplicate_tag_match(c) is True


# ── _has_duplicate_place (2026-08-12(2차), 같은 장소 중복 방문 하드룰) ────────


def test_has_duplicate_place_true_when_same_name_twice():
    c = _candidate(
        "A",
        [
            _activity("성수 브런치카페", start="10:00", end="11:00"),
            _activity("성수 브런치카페", start="14:00", end="15:00"),
        ],
    )
    assert _has_duplicate_place(c) is True


def test_has_duplicate_place_false_when_different_places():
    c = _candidate("A", [_activity("가게1"), _activity("가게2")])
    assert _has_duplicate_place(c) is False


def test_has_duplicate_place_true_even_without_matched_tag():
    # matched_tag가 둘 다 None이라 _has_duplicate_tag_match는 못 잡는 경우도
    # _has_duplicate_place는 이름만 보고 잡아야 한다.
    c = _candidate(
        "A",
        [
            _activity("가게1", matched_tag=None),
            _activity("가게1", matched_tag=None),
        ],
    )
    assert _has_duplicate_place(c) is True


# ── _has_excessive_travel (2026-08-11, 이동거리 하드룰) ────────────────────


def test_has_excessive_travel_true_for_distant_activities():
    # 서울(37.5, 127.0) -> 부산(35.1, 129.0), 약 300km 이상
    c = _candidate(
        "A",
        [
            _activity("가게1", lat=37.5, lng=127.0),
            _activity("가게2", lat=35.1, lng=129.0),
        ],
    )
    assert _has_excessive_travel(c) is True


def test_has_excessive_travel_false_for_nearby_activities():
    c = _candidate(
        "A",
        [
            _activity("가게1", lat=37.5000, lng=127.0000),
            _activity("가게2", lat=37.5010, lng=127.0010),
        ],
    )
    assert _has_excessive_travel(c) is False


def test_has_excessive_travel_true_when_over_fifteen_minute_estimate():
    # 남북 약 2.9km. 현재 직선거리 기반 보정식으로 16분이므로 하드 드롭해야 한다.
    c = _candidate(
        "A",
        [
            _activity("가게1", lat=37.500, lng=127.000),
            _activity("가게2", lat=37.526, lng=127.000),
        ],
    )

    assert _has_excessive_travel(c) is True


def test_has_excessive_travel_false_when_coordinates_missing():
    # 좌표 없는 활동(환각 장소)은 이미 _has_hallucinated_activity가 드롭하므로
    # 여기선 그냥 건너뛴다 — 크래시하면 안 됨.
    c = _candidate(
        "A",
        [
            _activity("가게1", lat=None, lng=None),
            _activity("가게2", lat=37.5, lng=127.0),
        ],
    )
    assert _has_excessive_travel(c) is False


# ── _has_missing_meal_slot (2026-08-11, 식사 슬롯 하드룰) ───────────────────


def test_required_meal_windows_both_when_range_spans_lunch_and_dinner():
    assert len(_required_meal_windows(_TIME_RANGE)) == 2  # 10:00~21:00


def test_required_meal_windows_empty_for_afternoon_only_range():
    assert _required_meal_windows(_CONDITIONS.time_range) == []  # 14:00~17:00


def test_has_missing_meal_slot_true_when_no_matgip_in_lunch_window():
    c = _candidate("A", [_activity("카페1", source_category="카페", start="12:00", end="13:00")])
    assert _has_missing_meal_slot(c, _MEAL_CONDITIONS) is True


def test_has_missing_meal_slot_false_when_matgip_covers_lunch_window():
    c = _candidate("A", [_activity("식당1", source_category="한식", start="12:00", end="13:00")])
    assert _has_missing_meal_slot(c, _LUNCH_ONLY_CONDITIONS) is False


def test_has_missing_meal_slot_false_when_no_meal_window_required():
    # _CONDITIONS는 14:00~17:00라 점심/저녁 슬롯 자체가 필요 없음
    c = _candidate("A", [_activity("카페1", source_category="카페")])
    assert _has_missing_meal_slot(c, _CONDITIONS) is False


def test_has_missing_meal_slot_true_when_dinner_missing_even_if_lunch_covered():
    c = _candidate("A", [_activity("식당1", source_category="한식", start="12:00", end="13:00")])
    # _MEAL_CONDITIONS(10:00~21:00)는 점심·저녁 둘 다 필요한데 저녁이 없음
    assert _has_missing_meal_slot(c, _MEAL_CONDITIONS) is True


def test_required_tags_drop_candidate_when_non_meal_tag_is_not_selected():
    candidate = _candidate(
        "A",
        [_activity("스테이크집", start="18:00", end="19:00", matched_tags=["스테이크"])],
    ).model_copy(update={"required_meal_tags": ["스테이크"], "required_non_meal_tags": ["와플"]})
    dinner_conditions = _CONDITIONS.model_copy(
        update={
            "time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 21, 0)),
            "liked_tags": [PreferenceTag(tag="스테이크", verifiable=True, is_meal=True)],
        }
    )

    assert _has_missing_required_tags(candidate, dinner_conditions) is True


def test_required_meal_tag_must_be_in_its_meal_slot():
    candidate = _candidate(
        "A",
        [_activity("스테이크집", start="15:00", end="16:00", matched_tags=["스테이크"])],
    ).model_copy(update={"required_meal_tags": ["스테이크"]})
    dinner_conditions = _CONDITIONS.model_copy(
        update={"time_range": (datetime(2026, 8, 15, 15, 0), datetime(2026, 8, 15, 21, 0))}
    )

    assert _has_missing_required_tags(candidate, dinner_conditions) is True


def test_rule_based_filter_drops_candidate_missing_meal_slot():
    dessert_only = _candidate(
        "디저트만",
        [_activity("카페1", source_category="카페", start="12:00", end="13:00")],
    )

    survivors, _ = _rule_based_filter([dessert_only], _MEAL_CONDITIONS)

    assert survivors == []


# ── _budget_overrun_ratio / _time_overrun_minutes ───────────────────────


def test_budget_overrun_ratio_zero_when_within_budget():
    c = _candidate("A", [_activity("가게1", price=(10000, 15000))])
    assert _budget_overrun_ratio(c, 50000) == 0.0


def test_budget_overrun_ratio_positive_when_over():
    c = _candidate("A", [_activity("가게1", price=(60000, 70000))])
    assert _budget_overrun_ratio(c, 50000) == (60000 - 50000) / 50000


def test_time_overrun_minutes_zero_when_within_range():
    c = _candidate("A", [_activity("가게1", start="10:00", end="11:00")])
    assert _time_overrun_minutes(c, _TIME_RANGE) == 0


def test_time_overrun_minutes_positive_when_over():
    c = _candidate("A", [_activity("가게1", start="20:30", end="21:30")])
    assert _time_overrun_minutes(c, _TIME_RANGE) == 30


# ── _rule_based_filter ───────────────────────────────────────────────────


def test_rule_based_filter_drops_hallucinated_candidate():
    good = _candidate("좋음", [_activity("가게1")])
    bad = _candidate("환각", [_activity("가게2", lat=None, lng=None)])

    survivors, _ = _rule_based_filter([good, bad], _CONDITIONS)

    assert survivors == [good]


def test_rule_based_filter_drops_time_overlap_candidate():
    overlapping = _candidate(
        "겹침",
        [
            _activity("가게1", start="10:00", end="11:30"),
            _activity("가게2", start="11:00", end="12:00"),
        ],
    )

    survivors, _ = _rule_based_filter([overlapping], _CONDITIONS)

    assert survivors == []


def test_rule_based_filter_drops_large_budget_overrun():
    # 예산 50000원의 20% 초과 = 60000원 초과분부터 드롭
    over = _candidate("초과", [_activity("가게1", price=(70000, 80000))])

    survivors, _ = _rule_based_filter([over], _CONDITIONS)

    assert survivors == []


def test_rule_based_filter_keeps_small_budget_overrun_with_warning():
    slightly_over = _candidate("약간초과", [_activity("가게1", price=(55000, 60000))])

    survivors, warnings = _rule_based_filter([slightly_over], _CONDITIONS)

    assert survivors == [slightly_over]
    assert "5000원" in warnings[0] or "5,000원" in warnings[0] or "원 더 필요" in warnings[0]


def test_rule_based_filter_keeps_normal_candidate_with_no_warning():
    normal = _candidate("정상", [_activity("가게1", price=(10000, 15000))])

    survivors, warnings = _rule_based_filter([normal], _CONDITIONS)

    assert survivors == [normal]
    assert warnings == [""]


def test_rule_based_filter_drops_candidate_with_duplicate_tag_match():
    dup = _candidate(
        "중복반영",
        [
            _activity("가게1", matched_tag="와플"),
            _activity("가게2", matched_tag="와플"),
        ],
    )

    survivors, _ = _rule_based_filter([dup], _CONDITIONS)

    assert survivors == []


def test_rule_based_filter_drops_candidate_with_duplicate_place():
    dup = _candidate(
        "중복방문",
        [
            _activity("성수 브런치카페", start="10:00", end="11:00"),
            _activity("성수 브런치카페", start="14:00", end="15:00"),
        ],
    )

    survivors, _ = _rule_based_filter([dup], _CONDITIONS)

    assert survivors == []


def test_rule_based_filter_drops_candidate_with_excessive_travel():
    far = _candidate(
        "너무멀음",
        [
            _activity("가게1", lat=37.5, lng=127.0),
            _activity("가게2", lat=35.1, lng=129.0),
        ],
    )

    survivors, _ = _rule_based_filter([far], _CONDITIONS)

    assert survivors == []


# ── synthesize_and_validate ──────────────────────────────────────────────


def _fake_judgment(*, keep_indices: set[int], why: str = "강점 설명", note: str = ""):
    def _call(**kwargs):
        n = kwargs["user"].count("candidate_index=")
        judgments = [
            _CandidateJudgment(
                candidate_index=i,
                keep=(i in keep_indices),
                why_recommended=why,
                feasibility_note=note,
            )
            for i in range(n)
        ]
        return _JudgmentBatch(judgments=judgments)

    return _call


def test_synthesize_and_validate_returns_infeasible_without_calling_llm_when_all_rule_dropped(
    monkeypatch,
):
    def fail_if_called(**kwargs):
        raise AssertionError("규칙 기반 필터로 다 드롭됐으면 LLM을 부르면 안 됨")

    monkeypatch.setattr("app.pipeline.synthesize_step3.call_structured", fail_if_called)

    hallucinated = _candidate("환각", [_activity("가게1", lat=None, lng=None)])

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, [hallucinated])

    assert isinstance(result, InfeasibleResponse)


def test_synthesize_and_validate_builds_schedule_response_from_llm_judgment(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices={0, 1})
    )
    candidates = [
        _candidate("첫번째", [_activity("가게1")]),
        _candidate("두번째", [_activity("가게2")]),
    ]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    assert isinstance(result, ScheduleResponse)
    assert result.session_id == "sess-1"
    assert len(result.candidates) == 2
    assert [c.candidate_id for c in result.candidates] == ["A", "B"]
    assert result.candidates[0].why_recommended == "강점 설명"


def test_synthesize_and_validate_drops_candidate_when_llm_keep_false(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices={0})
    )
    candidates = [
        _candidate("살아남음", [_activity("가게1")]),
        _candidate("드롭됨", [_activity("가게2")]),
    ]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    assert len(result.candidates) == 1
    assert result.candidates[0].title == "살아남음"


def test_synthesize_and_validate_returns_infeasible_when_llm_drops_all(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices=set())
    )
    candidates = [_candidate("드롭됨", [_activity("가게1")])]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    assert isinstance(result, InfeasibleResponse)


def test_synthesize_and_validate_combines_rule_and_llm_warnings(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured",
        _fake_judgment(keep_indices={0}, note="붐빌 수 있어요"),
    )
    slightly_over = _candidate("약간초과", [_activity("가게1", price=(55000, 60000))])

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, [slightly_over])

    warning = result.candidates[0].feasibility_warning
    assert "원 더 필요" in warning
    assert "붐빌 수 있어요" in warning


def test_synthesize_and_validate_routes_always_empty(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices={0})
    )
    candidates = [_candidate("A", [_activity("가게1")])]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    assert result.candidates[0].routes == []


def test_synthesize_and_validate_passes_through_matched_tag(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices={0})
    )
    candidates = [_candidate("A", [_activity("가게1", matched_tag="와플")])]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    assert result.candidates[0].activities[0].matched_tag == "와플"


def test_synthesize_and_validate_builds_map_url_from_address(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.synthesize_step3.call_structured", _fake_judgment(keep_indices={0})
    )
    candidates = [_candidate("A", [_activity("가게1")])]

    result = synthesize_and_validate("anthropic", "sk-fake", "sess-1", _CONDITIONS, candidates)

    activity = result.candidates[0].activities[0]
    assert activity.info_needs_check is True
    assert activity.map_url.startswith("https://map.naver.com/")

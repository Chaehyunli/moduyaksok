# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : generate_schedule_candidates() 테스트. normalize_conditions/
#              generate_candidates_with_perspectives/synthesize_and_validate/
#              generate_single_candidate는 전부 mock — 실제 LLM 판단이 아니라
#              "관점별 최대 1회 재시도" 오케스트레이션 로직만 검증한다.
# 작성일      : 2026-08-10
# ------------------------------------------------------------------
from datetime import datetime

from app.pipeline.orchestrate import generate_schedule_candidates
from app.pipeline.schemas import (
    Candidate,
    CandidateDraft,
    InfeasibleResponse,
    NormalizedConditions,
    ScheduleResponse,
)

_CONDITIONS = NormalizedConditions(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    region="서울 잠실",
    liked_tags=[],
    disliked_tags=[],
    budget_per_person=50000,
)

_RAW_INPUT = {"purpose": "date"}  # normalize_conditions는 mock되므로 내용 무의미


def _draft(title: str) -> CandidateDraft:
    return CandidateDraft(title=title, activities=[], rationale="r")


def _candidate(title: str) -> Candidate:
    return Candidate(candidate_id="A", title=title, why_recommended="w", activities=[], routes=[])


def _patch_common(monkeypatch, *, labeled_drafts):
    monkeypatch.setattr(
        "app.pipeline.orchestrate.normalize_conditions",
        lambda *a: _CONDITIONS,
    )

    async def fake_search_places_for_region(*a, **kwargs):
        return [{"title": "가게1"}]

    monkeypatch.setattr(
        "app.pipeline.orchestrate.search_places_for_region",
        fake_search_places_for_region,
    )

    async def fake_generate_with_perspectives(*a):
        return labeled_drafts

    monkeypatch.setattr(
        "app.pipeline.orchestrate.generate_candidates_with_perspectives",
        fake_generate_with_perspectives,
    )


async def test_returns_first_result_without_retry_when_nothing_missing(monkeypatch):
    labeled_drafts = [("가성비", _draft("A")), ("동선", _draft("B"))]
    _patch_common(monkeypatch, labeled_drafts=labeled_drafts)

    call_count = 0

    def fake_synthesize(*a):
        nonlocal call_count
        call_count += 1
        return ScheduleResponse(session_id="s1", candidates=[_candidate("A"), _candidate("B")])

    monkeypatch.setattr("app.pipeline.orchestrate.synthesize_and_validate", fake_synthesize)

    def fail_if_called(*a):
        raise AssertionError("빠진 관점이 없으면 재생성을 부르면 안 됨")

    monkeypatch.setattr("app.pipeline.orchestrate.generate_single_candidate", fail_if_called)

    result, conditions, place_candidates = await generate_schedule_candidates(
        "anthropic", "sk-fake", "s1", _RAW_INPUT
    )

    assert isinstance(result, ScheduleResponse)
    assert call_count == 1
    assert conditions is _CONDITIONS
    assert place_candidates == [{"title": "가게1"}]


async def test_retries_only_the_missing_perspective(monkeypatch):
    labeled_drafts = [
        ("가성비", _draft("A")),
        ("동선최소화", _draft("B")),
        ("취향반영", _draft("C")),
    ]
    _patch_common(monkeypatch, labeled_drafts=labeled_drafts)

    synth_calls: list[list[CandidateDraft]] = []

    def fake_synthesize(provider, api_key, session_id, conditions, candidates):
        synth_calls.append(candidates)
        if len(synth_calls) == 1:
            # "B"(동선최소화)가 하드 위반으로 드롭됨
            return ScheduleResponse(
                session_id=session_id, candidates=[_candidate("A"), _candidate("C")]
            )
        return ScheduleResponse(
            session_id=session_id, candidates=[_candidate(c.title) for c in candidates]
        )

    monkeypatch.setattr("app.pipeline.orchestrate.synthesize_and_validate", fake_synthesize)

    regen_calls = []

    def fake_generate_single(provider, api_key, conditions, place_candidates, perspective_label):
        regen_calls.append(perspective_label)
        return _draft("B-재생성")

    monkeypatch.setattr("app.pipeline.orchestrate.generate_single_candidate", fake_generate_single)

    result, _, _ = await generate_schedule_candidates("anthropic", "sk-fake", "s1", _RAW_INPUT)

    assert regen_calls == ["동선최소화"]
    assert len(synth_calls) == 2
    second_call_titles = {d.title for d in synth_calls[1]}
    assert second_call_titles == {"A", "C", "B-재생성"}
    assert isinstance(result, ScheduleResponse)
    assert {c.title for c in result.candidates} == {"A", "C", "B-재생성"}


async def test_gives_up_and_returns_original_result_when_regeneration_fails(monkeypatch):
    labeled_drafts = [("가성비", _draft("A")), ("동선최소화", _draft("B"))]
    _patch_common(monkeypatch, labeled_drafts=labeled_drafts)

    original_result = ScheduleResponse(session_id="s1", candidates=[_candidate("A")])
    monkeypatch.setattr(
        "app.pipeline.orchestrate.synthesize_and_validate", lambda *a: original_result
    )

    def failing_regenerate(*a):
        raise RuntimeError("재생성 실패")

    monkeypatch.setattr("app.pipeline.orchestrate.generate_single_candidate", failing_regenerate)

    result, _, _ = await generate_schedule_candidates("anthropic", "sk-fake", "s1", _RAW_INPUT)

    assert result is original_result


async def test_retries_all_perspectives_when_first_result_is_infeasible(monkeypatch):
    labeled_drafts = [("가성비", _draft("A")), ("동선최소화", _draft("B"))]
    _patch_common(monkeypatch, labeled_drafts=labeled_drafts)

    call_count = 0

    def fake_synthesize(provider, api_key, session_id, conditions, candidates):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return InfeasibleResponse(detail="d", reason="r", adjustable_conditions=[])
        return ScheduleResponse(
            session_id=session_id, candidates=[_candidate(c.title) for c in candidates]
        )

    monkeypatch.setattr("app.pipeline.orchestrate.synthesize_and_validate", fake_synthesize)

    regen_calls = []
    monkeypatch.setattr(
        "app.pipeline.orchestrate.generate_single_candidate",
        lambda provider, api_key, conditions, place_candidates, label: (
            regen_calls.append(label) or _draft(f"{label}-재생성")
        ),
    )

    result, _, _ = await generate_schedule_candidates("anthropic", "sk-fake", "s1", _RAW_INPUT)

    assert sorted(regen_calls) == ["가성비", "동선최소화"]
    assert isinstance(result, ScheduleResponse)


async def test_returns_infeasible_when_retry_also_fails(monkeypatch):
    labeled_drafts = [("가성비", _draft("A"))]
    _patch_common(monkeypatch, labeled_drafts=labeled_drafts)

    call_count = 0

    def fake_synthesize(provider, api_key, session_id, conditions, candidates):
        nonlocal call_count
        call_count += 1
        return InfeasibleResponse(detail="d", reason="r", adjustable_conditions=[])

    monkeypatch.setattr("app.pipeline.orchestrate.synthesize_and_validate", fake_synthesize)
    monkeypatch.setattr(
        "app.pipeline.orchestrate.generate_single_candidate",
        lambda provider, api_key, conditions, place_candidates, label: _draft("A-재생성"),
    )

    result, _, _ = await generate_schedule_candidates("anthropic", "sk-fake", "s1", _RAW_INPUT)

    assert isinstance(result, InfeasibleResponse)
    assert call_count == 2

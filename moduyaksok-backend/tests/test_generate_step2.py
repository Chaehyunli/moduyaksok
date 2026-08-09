# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : generate_candidates() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 만드는지가 아니라 우리 fan-out/조립/부분실패
#              처리 로직을 검증한다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime

import pytest

from app.pipeline.generate_step2 import (
    PERSPECTIVES,
    _build_system_prompt,
    _build_user_prompt,
    generate_candidates,
)
from app.pipeline.schemas import ActivityDraft, CandidateDraft, NormalizedConditions, PreferenceTag

_CONDITIONS = NormalizedConditions(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    region="서울 잠실",
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


def _fake_draft(perspective: str) -> CandidateDraft:
    return CandidateDraft(
        title=f"{perspective} 초안",
        activities=[
            ActivityDraft(
                name="잠실장어와 한우",
                category="한식",
                start_time="11:00",
                end_time="12:30",
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
        assert call["schema"] is CandidateDraft


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


def test_build_user_prompt_injects_place_candidates_and_conditions():
    prompt = _build_user_prompt(_CONDITIONS, _PLACE_CANDIDATES)

    assert "잠실장어와 한우" in prompt
    assert "OO카페" in prompt
    assert "서울 잠실" in prompt
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

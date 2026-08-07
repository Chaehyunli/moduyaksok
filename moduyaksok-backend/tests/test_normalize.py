# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : normalize_conditions() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 뽑는지가 아니라 우리 조립 로직을 검증한다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime

from app.pipeline.normalize import _ExtractedTags, normalize_conditions

_RAW_INPUT = {
    "purpose": "date",
    "headcount": 2,
    "time_range": [datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)],
    "region": "서울 잠실",
    "liked_text": "콩국수나 텐동, 와플 먹고 싶어",
    "disliked_text": "해산물은 못 먹어요",
    "budget_per_person": 50000,
}


def test_normalize_conditions_passes_through_already_structured_fields(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.normalize.call_structured",
        lambda **kwargs: _ExtractedTags(
            liked_tags=["콩국수", "텐동", "와플"], disliked_tags=["해산물"]
        ),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.purpose == "date"
    assert result.headcount == 2
    assert result.region == "서울 잠실"
    assert result.budget_per_person == 50000
    assert result.time_range == (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))


def test_normalize_conditions_uses_llm_extracted_tags(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.normalize.call_structured",
        lambda **kwargs: _ExtractedTags(
            liked_tags=["콩국수", "텐동", "와플"], disliked_tags=["해산물"]
        ),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.liked_tags == ["콩국수", "텐동", "와플"]
    assert result.disliked_tags == ["해산물"]


def test_normalize_conditions_passes_correct_tier_model_and_provider(monkeypatch):
    captured: dict = {}

    def fake_call_structured(**kwargs):
        captured.update(kwargs)
        return _ExtractedTags(liked_tags=[], disliked_tags=[])

    monkeypatch.setattr("app.pipeline.normalize.call_structured", fake_call_structured)

    normalize_conditions("upstage", "up-fake", _RAW_INPUT)

    assert captured["provider"] == "upstage"
    assert captured["api_key"] == "up-fake"
    assert captured["model"]  # get_model()이 뭘 반환하든 빈 값만 아니면 됨
    assert "콩국수" in captured["user"]
    assert "해산물" in captured["user"]


def test_normalize_conditions_handles_empty_preference_text(monkeypatch):
    captured: dict = {}

    def fake_call_structured(**kwargs):
        captured.update(kwargs)
        return _ExtractedTags(liked_tags=[], disliked_tags=[])

    monkeypatch.setattr("app.pipeline.normalize.call_structured", fake_call_structured)

    raw = {**_RAW_INPUT, "liked_text": "", "disliked_text": ""}
    result = normalize_conditions("anthropic", "sk-ant-fake", raw)

    assert result.liked_tags == []
    assert result.disliked_tags == []
    assert "(없음)" in captured["user"]

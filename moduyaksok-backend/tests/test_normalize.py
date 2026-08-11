# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : normalize_conditions() 테스트. call_structured는 mock —
#              LLM이 실제로 잘 뽑는지가 아니라 우리 조립 로직을 검증한다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, liked_tags/disliked_tags가 PreferenceTag(verifiable 포함)로 바뀐 것
#             반영
# ------------------------------------------------------------------
from datetime import datetime

from app.pipeline.normalize_step1 import _SYSTEM_PROMPT, _ExtractedTags, normalize_conditions
from app.pipeline.schemas import PreferenceTag

_RAW_INPUT = {
    "purpose": "date",
    "headcount": 2,
    "time_range": [datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)],
    "region": "서울 잠실",
    "liked_text": "콩국수나 텐동, 와플 먹고 싶어",
    "disliked_text": "해산물은 못 먹어요",
    "budget_per_person": 50000,
}

_SAMPLE_LIKED = [
    PreferenceTag(tag="콩국수", verifiable=True),
    PreferenceTag(tag="텐동", verifiable=True),
    PreferenceTag(tag="와플", verifiable=True),
]
_SAMPLE_DISLIKED = [PreferenceTag(tag="해산물", verifiable=True)]


def test_normalize_conditions_passes_through_already_structured_fields(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.normalize_step1.call_structured",
        lambda **kwargs: _ExtractedTags(liked_tags=_SAMPLE_LIKED, disliked_tags=_SAMPLE_DISLIKED),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.purpose == "date"
    assert result.headcount == 2
    assert result.region == "서울 잠실"
    assert result.budget_per_person == 50000
    assert result.time_range == (datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0))


def test_normalize_conditions_uses_llm_extracted_tags(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.normalize_step1.call_structured",
        lambda **kwargs: _ExtractedTags(liked_tags=_SAMPLE_LIKED, disliked_tags=_SAMPLE_DISLIKED),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.liked_tags == _SAMPLE_LIKED
    assert result.disliked_tags == _SAMPLE_DISLIKED


def test_normalize_conditions_preserves_verifiable_flag(monkeypatch):
    mixed = [
        PreferenceTag(tag="해산물", verifiable=True),
        PreferenceTag(tag="사람 많은 곳", verifiable=False),
    ]
    monkeypatch.setattr(
        "app.pipeline.normalize_step1.call_structured",
        lambda **kwargs: _ExtractedTags(liked_tags=[], disliked_tags=mixed),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.disliked_tags[0].verifiable is True
    assert result.disliked_tags[1].verifiable is False


def test_normalize_conditions_passes_correct_tier_model_and_provider(monkeypatch):
    captured: dict = {}

    def fake_call_structured(**kwargs):
        captured.update(kwargs)
        return _ExtractedTags(liked_tags=[], disliked_tags=[])

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fake_call_structured)

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

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fake_call_structured)

    raw = {**_RAW_INPUT, "liked_text": "", "disliked_text": ""}
    result = normalize_conditions("anthropic", "sk-ant-fake", raw)

    assert result.liked_tags == []
    assert result.disliked_tags == []
    assert "(없음)" in captured["user"]


def test_system_prompt_instructs_capping_verifiable_tags_at_max():
    # naver_local_search가 verifiable 태그 하나당 검색 1콜을 추가로 쓰게 되면서
    # (2026-08-11) 호출량 제어를 위해 Step1이 좋아하는/싫어하는 것 각각
    # MAX_VERIFIABLE_TAGS개까지만, 중요도 순으로 남기도록 지시해야 한다. 실제로
    # LLM이 이 지시를 잘 지키는지는 DeepEval 골든셋(eval)의 몫이라 여기선 지시문
    # 자체가 프롬프트에 있는지만 확인한다.
    from app.pipeline.schemas import MAX_VERIFIABLE_TAGS

    cap_text = f"최대 {MAX_VERIFIABLE_TAGS}개"
    assert cap_text in _SYSTEM_PROMPT
    assert "verifiable=false" in _SYSTEM_PROMPT.split(cap_text)[1][:200]

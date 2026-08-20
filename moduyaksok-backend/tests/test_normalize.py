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

from app.pipeline.normalize_step1 import (
    _SYSTEM_PROMPT,
    _ExtractedTags,
    _SemanticConflictBatch,
    detect_semantic_conflicts,
    dropped_verifiable_tags,
    normalize_conditions,
)
from app.pipeline.schemas import MAX_VERIFIABLE_TAGS, PreferenceTag

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
    PreferenceTag(tag="콩국수", verifiable=True, is_meal=True),
    PreferenceTag(tag="텐동", verifiable=True, is_meal=True),
    PreferenceTag(tag="와플", verifiable=True, is_meal=False),
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


def test_normalize_conditions_preserves_meal_classification(monkeypatch):
    tagged = [
        PreferenceTag(tag="스테이크", verifiable=True, is_meal=True),
        PreferenceTag(tag="소금빵", verifiable=True, is_meal=False),
    ]
    monkeypatch.setattr(
        "app.pipeline.normalize_step1.call_structured",
        lambda **kwargs: _ExtractedTags(liked_tags=tagged, disliked_tags=[]),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert [tag.is_meal for tag in result.liked_tags] == [True, False]


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


def test_system_prompt_explains_meal_and_snack_classification():
    assert "is_meal" in _SYSTEM_PROMPT
    assert "와플" in _SYSTEM_PROMPT
    assert "삼겹살" in _SYSTEM_PROMPT


def test_system_prompt_requires_preference_kind_and_priority():
    assert "preference_kind" in _SYSTEM_PROMPT
    assert "priority" in _SYSTEM_PROMPT
    assert "중요도 1~5" in _SYSTEM_PROMPT


def test_normalize_conditions_uses_resolved_tags_without_calling_llm(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError(
            "resolved_liked_tags/resolved_disliked_tags가 있으면 LLM을 부르면 안 됨"
        )

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fail_if_called)

    resolved_liked = [PreferenceTag(tag="초밥", verifiable=True, is_meal=True)]
    raw = {**_RAW_INPUT, "resolved_liked_tags": resolved_liked, "resolved_disliked_tags": []}

    result = normalize_conditions("anthropic", "sk-ant-fake", raw)

    assert result.liked_tags == resolved_liked
    assert result.disliked_tags == []


def test_normalize_conditions_falls_back_to_llm_when_no_resolved_tags(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.normalize_step1.call_structured",
        lambda **kwargs: _ExtractedTags(liked_tags=_SAMPLE_LIKED, disliked_tags=_SAMPLE_DISLIKED),
    )

    result = normalize_conditions("anthropic", "sk-ant-fake", _RAW_INPUT)

    assert result.liked_tags == _SAMPLE_LIKED


def test_dropped_verifiable_tags_returns_tags_beyond_cap():
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(MAX_VERIFIABLE_TAGS + 2)]

    dropped = dropped_verifiable_tags(tags)

    assert [t.tag for t in dropped] == [
        f"태그{MAX_VERIFIABLE_TAGS}",
        f"태그{MAX_VERIFIABLE_TAGS + 1}",
    ]


def test_dropped_verifiable_tags_ignores_non_verifiable():
    tags = [PreferenceTag(tag="조용한 곳", verifiable=False)]

    assert dropped_verifiable_tags(tags) == []


# ── detect_semantic_conflicts ───────────────────────────────────────────


def test_detect_semantic_conflicts_skips_llm_call_when_liked_empty(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("좋아요가 비었으면 LLM을 부르면 안 됨")

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fail_if_called)

    result = detect_semantic_conflicts("anthropic", "sk-ant-fake", [], ["해산물"])

    assert result == []


def test_detect_semantic_conflicts_skips_llm_call_when_disliked_empty(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("싫어요가 비었으면 LLM을 부르면 안 됨")

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fail_if_called)

    result = detect_semantic_conflicts("anthropic", "sk-ant-fake", ["초밥"], [])

    assert result == []


def test_detect_semantic_conflicts_returns_llm_result_when_both_sides_present(monkeypatch):
    captured: dict = {}

    def fake_call_structured(**kwargs):
        captured.update(kwargs)
        return _SemanticConflictBatch(
            conflicts=[
                {
                    "liked_tag": "초밥",
                    "disliked_tag": "해산물",
                    "explanation": "초밥은 해산물에 포함될 수 있어요",
                }
            ]
        )

    monkeypatch.setattr("app.pipeline.normalize_step1.call_structured", fake_call_structured)

    result = detect_semantic_conflicts("anthropic", "sk-ant-fake", ["초밥", "파스타"], ["해산물"])

    assert len(result) == 1
    assert result[0].liked_tag == "초밥"
    assert result[0].disliked_tag == "해산물"
    assert (
        "초밥" in captured["user"] and "파스타" in captured["user"] and "해산물" in captured["user"]
    )

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : NormalizedConditions.region 검증(세부지역 필수), verifiable 태그 상한 테스트
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-11(2차), regions: list[str] -> region: str 축소에 맞춰 지역 검증 테스트를
#             "세부지역 필수" 단일 값 검증으로 교체. MAX_VERIFIABLE_TAGS 3 -> 5에
#             맞춰 태그 상한 테스트도 하드코딩된 3 대신 상수를 참조하게 변경.
# ------------------------------------------------------------------
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.pipeline.schemas import MAX_VERIFIABLE_TAGS, NormalizedConditions, PreferenceTag

_BASE = dict(
    purpose="date",
    headcount=2,
    time_range=(datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)),
    liked_tags=[],
    disliked_tags=[],
    budget_per_person=50000,
)


def test_allows_region_with_district():
    result = NormalizedConditions(**_BASE, region="서울 잠실")

    assert result.region == "서울 잠실"


def test_rejects_broad_region_without_district():
    with pytest.raises(ValidationError, match="세부지역"):
        NormalizedConditions(**_BASE, region="서울")


# ── liked_tags/disliked_tags의 verifiable 태그 개수 상한(2026-08-11) ──────────

_TAG_BASE = {**_BASE, "region": "서울 잠실"}


def test_caps_verifiable_liked_tags_at_max():
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(MAX_VERIFIABLE_TAGS + 2)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS
    assert [t.tag for t in result.liked_tags] == [f"태그{i}" for i in range(MAX_VERIFIABLE_TAGS)]


def test_caps_verifiable_disliked_tags_independently_of_liked():
    liked = [PreferenceTag(tag="와플", verifiable=True)]
    disliked = [
        PreferenceTag(tag=f"싫음{i}", verifiable=True) for i in range(MAX_VERIFIABLE_TAGS + 1)
    ]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": liked, "disliked_tags": disliked})

    assert len(result.liked_tags) == 1
    assert len(result.disliked_tags) == MAX_VERIFIABLE_TAGS


def test_does_not_cap_non_verifiable_tags():
    tags = [
        PreferenceTag(tag=f"분위기{i}", verifiable=False) for i in range(MAX_VERIFIABLE_TAGS + 2)
    ]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS + 2


def test_cap_does_not_raise_validation_error():
    # region과 달리 태그 상한 초과는 요청을 실패시키지 않고 조용히 잘라야 한다
    # — LLM 품질 문제지 사용자가 검증을 우회하려는 상황이 아니기 때문
    # (schemas.py의 cap_verifiable_tags 주석 참고).
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(10)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS


def test_verifiable_and_non_verifiable_tags_both_survive_mixed_input():
    tags = [
        PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(MAX_VERIFIABLE_TAGS + 2)
    ] + [PreferenceTag(tag="분위기", verifiable=False)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS + 1
    assert any(t.tag == "분위기" for t in result.liked_tags)


def test_preference_priority_is_limited_to_one_through_five():
    assert PreferenceTag(tag="전시", verifiable=True, priority=5).priority == 5
    with pytest.raises(ValidationError):
        PreferenceTag(tag="전시", verifiable=True, priority=0)
    with pytest.raises(ValidationError):
        PreferenceTag(tag="전시", verifiable=True, priority=6)

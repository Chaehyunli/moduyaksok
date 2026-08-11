# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : NormalizedConditions.regions 검증(개수 제한, 포함관계 중복 제거) 테스트
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
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


def test_allows_one_broad_region_mixed_with_district_regions():
    result = NormalizedConditions(**_BASE, regions=["서울", "경기 수원", "경기 용인"])

    assert result.regions == ["서울", "경기 수원", "경기 용인"]


def test_allows_up_to_three_district_regions():
    result = NormalizedConditions(**_BASE, regions=["서울 잠실", "서울 성수"])

    assert result.regions == ["서울 잠실", "서울 성수"]


def test_allows_single_broad_region():
    result = NormalizedConditions(**_BASE, regions=["서울"])

    assert result.regions == ["서울"]


def test_rejects_two_broad_regions():
    with pytest.raises(ValidationError, match="시/도만"):
        NormalizedConditions(**_BASE, regions=["서울", "경기"])


def test_rejects_more_than_three_regions():
    with pytest.raises(ValidationError, match="최대 3개"):
        NormalizedConditions(**_BASE, regions=["서울 잠실", "서울 성수", "서울 강남", "서울 홍대"])


def test_rejects_empty_regions():
    with pytest.raises(ValidationError, match="최소 1개"):
        NormalizedConditions(**_BASE, regions=[])


def test_dedupes_district_region_contained_in_broad_region():
    result = NormalizedConditions(**_BASE, regions=["서울", "서울 잠실"])

    assert result.regions == ["서울"]


# ── liked_tags/disliked_tags의 verifiable 태그 개수 상한(2026-08-11) ──────────

_TAG_BASE = {**_BASE, "regions": ["서울 잠실"]}


def test_caps_verifiable_liked_tags_at_max():
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(5)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS
    assert [t.tag for t in result.liked_tags] == ["태그0", "태그1", "태그2"]


def test_caps_verifiable_disliked_tags_independently_of_liked():
    liked = [PreferenceTag(tag="와플", verifiable=True)]
    disliked = [PreferenceTag(tag=f"싫음{i}", verifiable=True) for i in range(4)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": liked, "disliked_tags": disliked})

    assert len(result.liked_tags) == 1
    assert len(result.disliked_tags) == MAX_VERIFIABLE_TAGS


def test_does_not_cap_non_verifiable_tags():
    tags = [PreferenceTag(tag=f"분위기{i}", verifiable=False) for i in range(5)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == 5


def test_cap_does_not_raise_validation_error():
    # regions와 달리 태그 상한 초과는 요청을 실패시키지 않고 조용히 잘라야 한다
    # — LLM 품질 문제지 사용자가 검증을 우회하려는 상황이 아니기 때문
    # (schemas.py의 cap_verifiable_tags 주석 참고).
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(10)]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS


def test_verifiable_and_non_verifiable_tags_both_survive_mixed_input():
    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(5)] + [
        PreferenceTag(tag="분위기", verifiable=False)
    ]

    result = NormalizedConditions(**{**_TAG_BASE, "liked_tags": tags, "disliked_tags": []})

    assert len(result.liked_tags) == MAX_VERIFIABLE_TAGS + 1
    assert any(t.tag == "분위기" for t in result.liked_tags)

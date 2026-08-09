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

from app.pipeline.schemas import NormalizedConditions

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
        NormalizedConditions(
            **_BASE, regions=["서울 잠실", "서울 성수", "서울 강남", "서울 홍대"]
        )


def test_rejects_empty_regions():
    with pytest.raises(ValidationError, match="최소 1개"):
        NormalizedConditions(**_BASE, regions=[])


def test_dedupes_district_region_contained_in_broad_region():
    result = NormalizedConditions(**_BASE, regions=["서울", "서울 잠실"])

    assert result.regions == ["서울"]

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : expand_broad_region() 테스트 — 세부지역 없는 광역 시/도를
#              세부지역 목록으로 펼치는 로직만 검증한다.
# 작성일      : 2026-08-11
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.services.regions import REGIONS, expand_broad_region


def test_expands_broad_region_into_prefixed_districts():
    result = expand_broad_region("서울")

    assert result == [f"서울 {d}" for d in REGIONS["서울"]]
    assert "서울 용산" in result


def test_does_not_expand_region_with_district_already():
    result = expand_broad_region("경기 수원")

    assert result == ["경기 수원"]


def test_returns_original_value_for_unknown_province():
    result = expand_broad_region("존재하지않는시도")

    assert result == ["존재하지않는시도"]


def test_returns_original_value_for_province_with_no_districts():
    # 세종은 REGIONS에 있지만 세부지역 목록이 비어있다.
    result = expand_broad_region("세종")

    assert result == ["세종"]

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : build_naver_map_url() 테스트. 네트워크 없이 URL 조립 로직만 검증 —
#              실제로 그 URL이 네이버 지도에서 장소를 보여주는지는 별도로 수동 확인함
#              (map.naver.com은 SPA라 HTTP 상태코드만으로는 검증 의미가 없고, 헤드리스
#              브라우저는 이 기능 하나 때문에 들이기엔 과함 — CI에 남기지 않기로 함).
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from app.services.naver_map_url import build_naver_map_url


def test_builds_url_from_title_and_road_address():
    from urllib.parse import unquote

    place = {"title": "잠실장어와 한우", "roadAddress": "서울 송파구 백제고분로7길"}

    url = build_naver_map_url(place)

    assert url.startswith("https://map.naver.com/p/search/")
    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "잠실장어와 한우 서울 송파구 백제고분로7길"


def test_falls_back_to_address_when_road_address_missing():
    from urllib.parse import unquote

    place = {"title": "OO카페", "address": "서울 송파구 잠실동"}

    url = build_naver_map_url(place)

    assert url.startswith("https://map.naver.com/p/search/")
    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "OO카페 서울 송파구 잠실동"


def test_prefers_road_address_over_address_when_both_present():
    place = {
        "title": "잠실 국숫집",
        "address": "서울 송파구 잠실동",
        "roadAddress": "서울 송파구 올림픽로 300",
    }

    url = build_naver_map_url(place)

    from urllib.parse import unquote

    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "잠실 국숫집 서울 송파구 올림픽로 300"


def test_handles_missing_address_fields_without_crashing():
    from urllib.parse import unquote

    place = {"title": "이름만 있는 장소"}

    url = build_naver_map_url(place)

    assert url.startswith("https://map.naver.com/p/search/")
    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "이름만 있는 장소"


def test_handles_completely_empty_place_without_crashing():
    url = build_naver_map_url({})

    assert url == "https://map.naver.com/p/search/"


def test_strips_floor_and_unit_from_road_address():
    from urllib.parse import unquote

    place = {
        "title": "노티드 여의도IFC몰",
        "roadAddress": "서울특별시 영등포구 국제금융로 10 L2층 234호",
    }

    url = build_naver_map_url(place)

    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "노티드 여의도IFC몰 서울특별시 영등포구 국제금융로 10"


def test_strips_basement_floor_only_no_unit():
    from urllib.parse import unquote

    place = {"title": "지하 카페", "roadAddress": "서울 강남구 테헤란로 1 지하1층"}

    url = build_naver_map_url(place)

    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "지하 카페 서울 강남구 테헤란로 1"


def test_trims_floor_and_repeated_store_name_after_road_number():
    from urllib.parse import unquote

    place = {
        "title": "츄플러스",
        "roadAddress": "경기 수원시 팔달구 화서문로45번길 26 1층 츄플러스",
    }

    url = build_naver_map_url(place)

    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == "츄플러스 경기 수원시 팔달구 화서문로45번길 26"


def test_trims_building_name_and_floor_range_after_road_number():
    from urllib.parse import unquote

    place = {
        "title": "아이엠제이 브런치카페 수원성균관대역점",
        "roadAddress": "경기도 수원시 장안구 화산로285번길 18-1 더크리스탈 지하1-지상1층",
    }

    url = build_naver_map_url(place)

    decoded = unquote(url.removeprefix("https://map.naver.com/p/search/"))
    assert decoded == (
        "아이엠제이 브런치카페 수원성균관대역점 경기도 수원시 장안구 화산로285번길 18-1"
    )

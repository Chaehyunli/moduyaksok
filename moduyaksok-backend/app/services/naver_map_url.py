# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 네이버 지역검색 결과(place dict)로 네이버 지도 검색 URL 조립.
#              좌표(mapx/mapy) 변환 없이 이름+주소로 검색되는 링크를 만든다 —
#              place_candidates는 이미 네이버 검색이 실존을 확인한 데이터라
#              이름+주소만으로도 신뢰할 수 있는 링크가 나온다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from urllib.parse import quote

_MAP_SEARCH_URL = "https://map.naver.com/p/search/"


def build_naver_map_url(place: dict) -> str:
    """place(네이버 지역검색 결과 항목 — title/address/roadAddress 등)로 네이버
    지도 검색 URL을 만든다. roadAddress가 있으면 우선 쓰고, 없으면 address로
    대체한다. 좌표(mapx/mapy)는 네이버 내부 좌표계라 WGS84 변환이 필요한데,
    이름+주소 검색은 그 변환 없이도 신뢰할 수 있는 링크를 만든다.
    """
    title = place.get("title", "")
    address = place.get("roadAddress") or place.get("address", "")
    query = f"{title} {address}".strip()
    return _MAP_SEARCH_URL + quote(query)

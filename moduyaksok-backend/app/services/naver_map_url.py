# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 네이버 지역검색 결과(place dict)로 네이버 지도 검색 URL 조립.
#              좌표(mapx/mapy) 변환 없이 이름+주소로 검색되는 링크를 만든다 —
#              place_candidates는 이미 네이버 검색이 실존을 확인한 데이터라
#              이름+주소만으로도 신뢰할 수 있는 링크가 나온다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, roadAddress에 "L2층 234호" 같은 층/호수까지 붙어있으면 네이버 지도
#             텍스트 검색이 그 장소를 못 찾는 경우 확인(실측, "노티드 여의도IFC몰") —
#             검색 쿼리에서는 층/호수를 떼어내도록 수정.
# 2026-08-11, 층/호수 뒤에 건물명·상호가 이어지는 주소도 확인 — 도로명과 건물번호
#             (예: "화서문로45번길 26")까지만 검색 쿼리에 사용하도록 보완.
# ------------------------------------------------------------------
import re
from urllib.parse import quote

_MAP_SEARCH_URL = "https://map.naver.com/p/search/"

# 주소 끝에 붙는 층/호수 토큰만 골라 지운다 ("L2층", "지하1층", "234호" 등).
# 도로명 주소를 인식하지 못하는 예외 주소의 보조 처리로 사용한다.
_FLOOR_OR_UNIT_TOKEN_RE = re.compile(r"^(지하)?[A-Za-z가-힣]{0,3}\d+(층|호)$")

# 네이버 지도 검색에서는 건물명·층·호수·상호가 도로명 주소 뒤에 붙으면 결과를
# 놓치는 경우가 있다. 마지막 도로명(대로/로/길)과 실제 건물번호까지만 취한다.
# `화서문로45번길 26`처럼 도로명 안에도 숫자가 있는 경우를 위해, 건물번호 뒤에는
# 공백 또는 문자열 끝이 와야 한다.
_ROAD_ADDRESS_CORE_RE = re.compile(r"^(.+(?:대로|로|길)\s*\d+(?:-\d+)?)(?=\s|$)")


def _strip_floor_and_unit(address: str) -> str:
    tokens = address.split()
    while tokens and _FLOOR_OR_UNIT_TOKEN_RE.match(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _trim_to_searchable_road_address(address: str) -> str:
    """도로명 주소가 있으면 도로명+건물번호만, 없으면 기존 층/호수 정리를 쓴다."""
    address = address.strip()
    match = _ROAD_ADDRESS_CORE_RE.match(address)
    if match:
        return match.group(1)
    return _strip_floor_and_unit(address)


def build_naver_map_url(place: dict) -> str:
    """place(네이버 지역검색 결과 항목 — title/address/roadAddress 등)로 네이버
    지도 검색 URL을 만든다. roadAddress가 있으면 우선 쓰고, 없으면 address로
    대체한다. 층/호수 같은 세부 단위는 검색에 방해가 되니 떼어낸다(아래 참고).
    좌표(mapx/mapy)는 네이버 내부 좌표계라 WGS84 변환이 필요한데, 이름+주소
    검색은 그 변환 없이도 신뢰할 수 있는 링크를 만든다.
    """
    title = place.get("title", "")
    address = place.get("roadAddress") or place.get("address", "")
    address = _trim_to_searchable_road_address(address)
    query = f"{title} {address}".strip()
    return _MAP_SEARCH_URL + quote(query)

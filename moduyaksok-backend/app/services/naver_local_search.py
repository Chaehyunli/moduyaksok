# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : 네이버 지역검색 API 호출. Step2가 LLM에 넘길 place_candidates를
#              만드는 데 쓰는 사전 조회 — LLM이 모르는 장소를 지어내지 않도록
#              실제 존재하는 장소 목록을 먼저 확보한다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, 레거시 openapi.naver.com 엔드포인트로 실측했다가 401 발생 —
#             2026-07-31부로 검색 API가 NAVER API HUB(NCP)로 이관되면서
#             엔드포인트 도메인과 인증 헤더 이름이 바뀐 것으로 확인(실측+문서
#             확인). X-Naver-Client-Id/Secret이 아니라
#             X-NCP-APIGW-API-KEY-ID/X-NCP-APIGW-API-KEY를 쓴다.
# 2026-08-09, search_places_for_regions() 추가 — regions(최대 3개)를 받아 지역×
#             카테고리(_PLACE_CATEGORIES)로 팬아웃 검색 후 title 기준 중복 제거해
#             병합. search_places() 자체는 안 건드림. 이 함수를 부를 POST /schedules
#             라우터는 아직 없음(Step2와 같은 패턴 — 함수 먼저, 라우터는 나중).
# ------------------------------------------------------------------
import asyncio
import re

import httpx

from app.config import settings

# 검색어와 일치하는 부분에 네이버가 <b> 태그를 강조 표시로 넣어서 돌려준다(실측
# 확인, 2026-08-09) — Step2 프롬프트에 그대로 넣으면 LLM이 HTML 태그를 실제
# 장소명의 일부로 오해할 수 있어 벗겨낸다.
_TAG_RE = re.compile(r"<[^>]+>")

_SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search/v1/local"

# NAVER API HUB 이관 후 display 허용 범위가 1~5로 줄었다(레거시 API는 더 컸음) —
# 지역 하나당 한 번의 호출로 최대 5개까지만 받을 수 있다는 뜻. 카테고리별로 여러
# 번 호출해서 place_candidates를 채우는 구조가 되어야 한다(호출부 책임).
_MAX_DISPLAY = 5


class NaverSearchError(Exception):
    """네이버 지역검색 API 호출 실패(인증 오류, 타임아웃, 5xx 등)."""


async def search_places(query: str, display: int = _MAX_DISPLAY) -> list[dict]:
    """query로 네이버 지역검색을 호출해 장소 후보 목록을 반환한다.

    결과가 없는 건 에러가 아니다 — 그 카테고리에 후보가 없다는 뜻이라 빈 리스트를
    그대로 반환한다. 호출 자체가 실패한 경우(인증 오류, 타임아웃, 5xx)만
    NaverSearchError로 감싸서 올린다. 이 API는 네이버 지도 API(Step3가 쓸
    NAVER_MAP_CLIENT_ID/SECRET)와 다른 상품이라 별도 키(NAVER_SEARCH_CLIENT_ID/
    SECRET)를 쓴다.
    """
    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_search_client_id,
        "X-NCP-APIGW-API-KEY": settings.naver_search_client_secret,
    }
    params = {"query": query, "display": min(display, _MAX_DISPLAY), "sort": "comment"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NaverSearchError(f"네이버 지역검색 호출 실패: {exc}") from exc

    items = response.json().get("items", [])
    for item in items:
        item["title"] = _TAG_RE.sub("", item.get("title", ""))
        item["description"] = _TAG_RE.sub("", item.get("description", ""))
    return items


# region마다 이 카테고리들로 각각 검색해서 place_candidates를 채운다. 실제 사용
# 데이터 보고 필요한 카테고리 추가/조정할 것(REGIONS 목록과 같은 원칙).
_PLACE_CATEGORIES = ("맛집", "카페", "액티비티", "문화시설")


async def search_places_for_regions(regions: list[str]) -> list[dict]:
    """regions(최대 3개, 호출부가 이미 검증했다고 가정) 각각에 대해
    _PLACE_CATEGORIES로 병렬 검색하고 title 기준으로 중복 제거해 병합한다.

    "서울"처럼 시/도만 있는 넓은 지역과 "서울 잠실"처럼 세부지역까지 있는 좁은
    지역을 구분하지 않고 동일하게 처리한다 — query 문자열에 그대로 이어붙일 뿐이라
    네이버 지역검색이 알아서 관련도 순으로 걸러준다(display=5로 이미 상한).
    """
    queries = [f"{region} {category}" for region in regions for category in _PLACE_CATEGORIES]
    results_per_query = await asyncio.gather(
        *(search_places(query) for query in queries), return_exceptions=True
    )

    merged: dict[str, dict] = {}
    for result in results_per_query:
        if isinstance(result, BaseException):
            continue
        for place in result:
            merged.setdefault(place["title"], place)
    return list(merged.values())

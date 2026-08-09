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
# ------------------------------------------------------------------
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

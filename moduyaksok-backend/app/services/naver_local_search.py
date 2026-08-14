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
# 2026-08-11, "와플" 태그가 있는데 실제로 와플이 없는 카페가 verifiable=true로
#             하드 반영되는 정밀도 문제(2026-08-10 미해결 설계 질문) 해결 + 세부지역
#             없는 광역 시/도 자동 확장, 두 가지를 같이 반영:
#             - liked_tags/disliked_tags 중 verifiable=true인 태그마다
#               "{region} {tag}" 검색을 카테고리 검색과 별도로 추가 호출한다.
#               지금까진 category/title 텍스트만 보고 LLM이 사후 추측했는데,
#               "이 태그로 검색하면 실제로 뜨는 곳"이라는 더 강한 근거로 대체 —
#               liked 매칭 결과는 place dict에 matched_tags를 부착해 "이 태그들을
#               만족하는 후보"로 인정한다. 하위 호환을 위해 첫 태그는 matched_tag로
#               유지한다(Step2가 참고, Step3가 같은 태그 중복 반영을
#               판단하는 근거), disliked 매칭 결과는 애초에 결과 목록에서 제거해
#               Step2 LLM이 볼 수도 없게 한다(카테고리/제목 텍스트로 사후 배제하던
#               것보다 강한 보장).
#             - 세부지역 없이 시/도만 입력된 region("서울")은 app.services.regions
#               의 세부지역 목록으로 펼쳐서 각각 독립적으로 검색한다(카테고리 5개
#               고정 유지, 페이지네이션은 이 API가 start를 무시해서 실측으로
#               불가능 확인함).
#             - 호출량이 태그·지역 확장과 곱해져 순간적으로 네이버 API HUB
#               한도(초당 10건, 일일 25,000건)를 크게 넘길 수 있어
#               app/services/rate_limiter.py 도입 — search_places()가 호출 하나마다
#               초당 상한을 기다리고, search_places_for_regions()가 쿼리를 쏘기
#               전에 일일 예산을 먼저 확보한다(부족하면 확보되는 만큼만 검색해
#               place_candidates가 적은 채로 진행 — 2026-08-11 결정, 하드 실패보다
#               부분 결과가 낫다는 판단).
# 2026-08-11, 카테고리 쿼리에도 매칭값을 부착 — 지금까진 (query, kind, tag)
#             튜플에서 카테고리 쿼리는 항상 tag=None이었는데, 그 자리에 카테고리
#             이름 자체("맛집" 등)를 넣어 place dict에 source_category로 부착한다.
#             Step2가 "이 활동이 어느 검색 버킷에서 나왔는지"(카페 검색으로만
#             나온 곳인지, 맛집 검색으로 나온 곳인지)를 결정론적으로 알아야
#             점심/저녁 시간대에 실제 식사류를 채울 수 있다 — 네이버 원본
#             category 문자열은 카페도 "음식점>카페,디저트"로 묶여있어(실측 확인)
#             이걸로는 "식사 가능한 곳"과 "디저트만 되는 곳"을 못 가른다. tag와
#             같은 방식(우리가 무슨 쿼리로 찾았는지)이 더 신뢰할 수 있는 근거.
# 2026-08-11(2차), NAVER API HUB 공식 문서로 display(1~5)/start(사실상 고정)
#             제한을 재확인 — 여러 지역을 조합해서 받던 걸 세부지역 필수 단일
#             region으로 좁히고(regions.py 삭제, expand_broad_region 제거),
#             대신 _PLACE_CATEGORIES를 4개("맛집/카페/액티비티/문화시설")에서
#             15개로 세분화 + MAX_VERIFIABLE_TAGS 5로 상향해서 지역 하나당
#             카테고리·태그 쿼리 팬아웃만으로 최소 50개 이상의 고유 장소를
#             모으게 했다(사용자 결정 — start 페이지네이션이 막혀있으니 쿼리
#             다양화로 대신한다). search_places_for_regions() ->
#             search_places_for_region()으로 개명(단수 지역만 받게 됨).
# 2026-08-13, reserve_daily_budget()이 resource/daily_limit을 인자로 받게
#             일반화됨(Step4의 ODsay 일일 한도 추가와 함께, rate_limiter.py 참고)
#             — 이 파일의 호출부만 "naver_search"/settings.naver_daily_call_limit을
#             명시적으로 넘기게 갱신, 동작 자체는 그대로다.
# 2026-08-12, 쿼리(카테고리·태그)마다 sort="comment"(리뷰순) 한 번만 부르던 걸
#             sort="random"(정확도순, 네이버 지도 앱 기본 정렬에 더 가까움)까지
#             같이 불러서 병합하도록 변경(사용자 결정) — 리뷰순만 쓰면 리뷰가
#             적지만 관련도 높은 곳이 5개 상한에 밀려 아예 안 잡히는 문제가 있어,
#             정렬 기준이 다른 두 결과를 모아 title로 dedup하면 커버리지가
#             넓어진다는 판단. 쿼리 수가 그대로 2배가 돼 일일 호출 예산 소모도
#             2배가 된다 — reserve_daily_budget() 예산이 부족하면 기존과 동일하게
#             뒤쪽(태그 쿼리부터) 잘려서 부분 결과로 진행된다.
# 2026-08-12(2차), 같은 장소가 여러 liked 태그 검색 결과에 함께 나올 때 첫
#             태그만 남기던 정보를 matched_tags 배열로 보존. 기존 API 소비자와
#             저장된 세션 호환을 위해 matched_tag에는 첫 태그도 계속 제공한다.
# ------------------------------------------------------------------
import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass

import httpx

from app.config import settings
from app.pipeline.schemas import MAX_VERIFIABLE_TAGS, PreferenceTag
from app.services.naver_map_url import build_naver_map_url
from app.services.rate_limiter import acquire_call_slot, reserve_daily_budget

logger = logging.getLogger(__name__)

# 검색어와 일치하는 부분에 네이버가 <b> 태그를 강조 표시로 넣어서 돌려준다(실측
# 확인, 2026-08-09) — Step2 프롬프트에 그대로 넣으면 LLM이 HTML 태그를 실제
# 장소명의 일부로 오해할 수 있어 벗겨낸다.
_TAG_RE = re.compile(r"<[^>]+>")

_SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search/v1/local"

# NAVER API HUB 이관 후 display 허용 범위가 1~5로 줄었다(레거시 API는 더 컸음) —
# 지역 하나당 한 번의 호출로 최대 5개까지만 받을 수 있다는 뜻. 카테고리별로 여러
# 번 호출해서 place_candidates를 채우는 구조가 되어야 한다(호출부 책임).
_MAX_DISPLAY = 5

# 쿼리마다 이 두 정렬로 각각 한 번씩 호출해서 병합한다 — "random"은 이름과 달리
# 정확도순(네이버 공식 문서), "comment"는 리뷰 많은 순. 정렬 기준이 다른 결과를
# 모으면 한쪽만 쓸 때보다 5개 상한에 안 걸리고 잡히는 장소가 늘어난다.
_SORT_RANDOM = "random"
_SORT_COMMENT = "comment"
_SORTS = (_SORT_RANDOM, _SORT_COMMENT)


class NaverSearchError(Exception):
    """네이버 지역검색 API 호출 실패(인증 오류, 타임아웃, 5xx 등)."""


@dataclass
class PlaceSearchResult(list[dict]):
    """Step2가 사용할 안전한 장소 목록과, 사용자에게 보여줄 검색 이력.

    list를 상속해 기존 파이프라인이 ``list[dict]``처럼 그대로 사용할 수 있게
    유지한다. ``search_groups``에는 각 검색 질의의 결과를 별도로 보존한다. 특히
    disliked 검색 결과는 Step2 입력에서는 제거되지만, 사용자가 "왜 이 장소는
    후보에서 빠졌는지" 확인할 수 있도록 이력에는 남긴다.
    """

    search_groups: dict

    def __init__(self, places: list[dict], search_groups: dict):
        super().__init__(places)
        self.search_groups = search_groups


async def search_places(
    query: str,
    display: int = _MAX_DISPLAY,
    session_id: str = "",
    sort: str = _SORT_COMMENT,
) -> list[dict]:
    """query로 네이버 지역검색을 호출해 장소 후보 목록을 반환한다.

    결과가 없는 건 에러가 아니다 — 그 카테고리에 후보가 없다는 뜻이라 빈 리스트를
    그대로 반환한다. 호출 자체가 실패한 경우(인증 오류, 타임아웃, 5xx)만
    NaverSearchError로 감싸서 올린다. 이 API는 Step4가 쓰는 ODsay 대중교통 길찾기
    API와 다른 상품이라 별도 키(NAVER_SEARCH_CLIENT_ID/SECRET)를 쓴다.

    session_id는 rate_limiter의 라운드로빈 공평성 키다(2026-08-11) — 어느
    `POST /schedules` 요청에서 나온 호출인지 구분해서, 동시에 여러 요청이 콜을
    쏟아낼 때 한쪽이 다른 쪽을 굶기지 않게 한다. 이 함수를 단독으로 부르는
    곳(테스트 등)은 기본값("")을 그냥 같은 세션으로 취급해도 무방하다.
    """
    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_search_client_id,
        "X-NCP-APIGW-API-KEY": settings.naver_search_client_secret,
    }
    params = {"query": query, "display": min(display, _MAX_DISPLAY), "sort": sort}

    try:
        await acquire_call_slot(session_id)
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


# region 하나에 이 카테고리들로 각각 검색해서 place_candidates를 채운다.
# 2026-08-11(2차) 세분화: "맛집" 하나로 뭉쳐두면 카테고리당 display 상한(5개)에
# 막혀 식사류 전체가 5곳으로 제한됐다 — 요리별로 쪼개면 쿼리 수만큼 5개씩 더
# 받을 수 있다(카테고리 결과끼리는 겹치는 장소가 거의 없어 보여 세분화해도
# 손해가 없다는 게 사용자 판단, title 기준 dedup이 그래도 있을 중복은 처리).
# 이 목록 × 태그 쿼리(최대 MAX_VERIFIABLE_TAGS×2개)를 합치면 지역 하나당
# 최소 50개 이상의 고유 장소를 모으는 게 목표(2026-08-11(2차) 결정) — 네이버
# API의 start 페이지네이션이 사실상 고정이라(공식 문서로 확인) 그쪽으론 늘릴
# 수 없어서 쿼리 팬아웃으로 대신한다. 실제 사용 데이터 보고 계속 추가/조정할 것.
_PLACE_CATEGORIES = (
    "한식",
    "중식",
    "일식",
    "양식",
    "분식",
    "고깃집",
    "카페",
    "베이커리",
    "술집",
    "액티비티",
    "방탈출",
    "보드게임카페",
    "전시",
    "공연장",
    "영화관",
)

# _PLACE_CATEGORIES 중 "식사가 되는" 카테고리만 — synthesize_step3.py의
# _has_missing_meal_slot과 generate_step2.py의 프롬프트 안내문이 "점심/저녁
# 시간대에 식사류가 있는지"를 판단할 때 이 집합과 ActivityDraft.source_category를
# 비교한다(카페/베이커리/술집은 디저트·주류 위주라 "식사"로 안 침). 카테고리
# 목록을 바꿀 땐 이 집합도 같이 확인할 것.
_MEAL_CATEGORIES = frozenset({"한식", "중식", "일식", "양식", "분식", "고깃집"})

# (query, kind, value) 튜플에서 kind로 쓰는 상수. value는 kind별로 뜻이 다르다 —
# category는 카테고리 이름 자체("한식" 등), liked/disliked는 태그 문자열.
_KIND_CATEGORY = "category"
_KIND_LIKED = "liked"
_KIND_DISLIKED = "disliked"


def _build_queries(
    region: str,
    liked_tags: list[PreferenceTag],
    disliked_tags: list[PreferenceTag],
) -> list[tuple[str, str, str | None, str]]:
    """(query 문자열, kind, value, sort) 리스트를 만든다. 카테고리 쿼리를 항상 먼저
    두고 태그 쿼리를 뒤에 두는 순서가 중요하다 — 일일 예산이 부족해 뒤쪽이 잘려도
    "일정의 뼈대"인 카테고리 검색이 먼저 살아남게 하기 위함(2026-08-11 결정,
    태그 검색은 정밀도 보강일 뿐 필수 커버리지가 아니다). 같은 쿼리 문자열을
    _SORTS 각각으로 바로 이어 붙여서, 예산이 중간에 잘려도 같은 쿼리의 두 정렬이
    최대한 같이 살아남거나 같이 잘리게 한다(2026-08-12).
    """
    liked = [t.tag for t in liked_tags if t.verifiable][:MAX_VERIFIABLE_TAGS]
    disliked = [t.tag for t in disliked_tags if t.verifiable][:MAX_VERIFIABLE_TAGS]

    base: list[tuple[str, str, str | None]] = [
        (f"{region} {c}", _KIND_CATEGORY, c) for c in _PLACE_CATEGORIES
    ]
    base.extend((f"{region} {tag}", _KIND_LIKED, tag) for tag in liked)
    base.extend((f"{region} {tag}", _KIND_DISLIKED, tag) for tag in disliked)
    # 일반 카테고리는 정확도순 5곳이면 일정 재료가 충분하다. 좋아요/싫어요 태그는
    # 놓치면 하드 조건 판정이 달라지므로 두 정렬을 유지한다. 기본 15개 카테고리와
    # 좋아요 2개·싫어요 1개라면 36회에서 21회로 줄어든다.
    return [
        (query, kind, value, sort)
        for query, kind, value in base
        for sort in ((_SORT_RANDOM,) if kind == _KIND_CATEGORY else _SORTS)
    ]


def _merge_results(
    queries: list[tuple[str, str, str | None, str]],
    results: list[list[dict] | BaseException],
) -> tuple[dict[str, dict], bool]:
    """title 기준 병합. liked 쿼리에서 나온 장소엔 matched_tags와 하위 호환용
    matched_tag를, 카테고리 쿼리에서
    나온 장소엔 source_category를 부착한다. disliked 쿼리에서 나온 장소는
    (카테고리 검색에서도 같이 나왔더라도) 최종 결과에서 제거한다 — Step2 LLM이
    disliked 장소를 아예 볼 수 없게 하는 게 "category/title 텍스트로 사후
    배제해라"는 프롬프트 지시보다 강한 보장이다. 같은 쿼리를 sort만 다르게 두 번
    부른 결과(2026-08-12)도 title이 같으면 여기서 자연히 하나로 합쳐진다.
    """
    merged: dict[str, dict] = {}
    liked_title_to_tags: dict[str, list[str]] = {}
    category_title_to_bucket: dict[str, str] = {}
    disliked_titles: set[str] = set()
    any_failed = False

    for (_, kind, value, _sort), result in zip(queries, results, strict=True):
        if isinstance(result, BaseException):
            any_failed = True
            continue
        for place in result:
            title = place["title"]
            merged.setdefault(title, place)
            if kind == _KIND_LIKED and value is not None:
                tags = liked_title_to_tags.setdefault(title, [])
                if value not in tags:
                    tags.append(value)
            elif kind == _KIND_DISLIKED:
                disliked_titles.add(title)
            elif kind == _KIND_CATEGORY and value is not None:
                category_title_to_bucket.setdefault(title, value)

    for title, tags in liked_title_to_tags.items():
        if title in merged:
            merged[title]["matched_tags"] = tags
            # 기존 소비자는 단일 값만 읽고 있어 첫 태그도 계속 제공한다.
            merged[title]["matched_tag"] = tags[0]
    for title, bucket in category_title_to_bucket.items():
        if title in merged:
            merged[title].setdefault("source_category", bucket)
    for title in disliked_titles:
        merged.pop(title, None)

    return merged, any_failed


def _to_snapshot_place(place: dict) -> dict:
    """검색 이력 화면에 필요한 공개 가능한 최소 장소 정보만 남긴다."""
    address = place.get("roadAddress") or place.get("address", "")
    return {
        "place_id": place_id_for(place),
        "name": place.get("title", ""),
        "category": place.get("category", ""),
        "address": address,
        "map_url": build_naver_map_url(place),
    }


def place_id_for(place: dict) -> str:
    """검색 결과 안에서 장소를 안정적으로 가리키는 식별자를 만든다.

    지역검색 응답의 ``link``/지도 place id는 항상 제공되지 않아 믿을 수 없다. 반면
    제목과 도로명 주소는 후보 목록·지도 링크 모두에 쓰이는 값이므로, 두 값을 정규화
    해 SHA-256으로 만든 ID를 선택·해제 API의 공개 식별자로 쓴다. 원본 제목은 같은
    이름의 지점이 있을 수 있어 주소 없이 쓰지 않는다.
    """
    title = " ".join(str(place.get("title") or place.get("name", "")).split())
    address = " ".join(str(place.get("roadAddress") or place.get("address", "")).split())
    return hashlib.sha256(f"{title}\x1f{address}".encode()).hexdigest()


def _build_search_groups(
    queries: list[tuple[str, str, str | None, str]],
    results: list[list[dict] | BaseException],
    eligible_titles: set[str],
) -> dict:
    """검색 시점의 질의별 결과를 UI/피드백 재사용용 JSON으로 정리한다.

    카테고리와 좋아요 그룹은 실제 Step2에 남긴 안전한 장소만 보여준다. 싫어요
    그룹만은 의도적으로 제외 전 원본을 남겨, 해당 검색이 어떤 장소를 차단했는지
    투명하게 확인할 수 있게 한다. 같은 (kind, value)가 sort별로 두 번 나오므로
    (2026-08-12) label별로 먼저 모아 title 기준 dedup한 뒤에 그룹을 만든다 —
    안 그러면 같은 라벨("한식" 등)의 그룹이 두 번 생긴다.
    """
    label_places: dict[tuple[str, str], dict[str, dict]] = {}
    label_order: list[tuple[str, str]] = []

    for (_, kind, value), result in zip(
        ((q, k, v) for q, k, v, _sort in queries), results, strict=True
    ):
        if isinstance(result, BaseException) or value is None:
            continue
        key = (kind, value)
        if key not in label_places:
            label_places[key] = {}
            label_order.append(key)
        for place in result:
            if kind != _KIND_DISLIKED and place.get("title") not in eligible_titles:
                continue
            snapshot = _to_snapshot_place(place)
            label_places[key].setdefault(snapshot["name"], snapshot)

    grouped: dict[str, list[dict]] = {
        "liked": [],
        "disliked": [],
        "categories": [],
    }
    for kind, value in label_order:
        places = list(label_places[(kind, value)].values())
        if not places:
            continue
        group = {"label": value, "places": places}
        if kind == _KIND_CATEGORY:
            grouped["categories"].append(group)
        else:
            grouped[kind].append(group)

    return {
        "candidate_count": len(eligible_titles),
        "groups": grouped,
    }


async def search_places_for_region(
    region: str,
    liked_tags: list[PreferenceTag] | None = None,
    disliked_tags: list[PreferenceTag] | None = None,
    session_id: str = "",
) -> list[dict]:
    """region(세부지역 포함 단일 값, 호출부가 이미 검증했다고 가정) 하나에 대해
    _PLACE_CATEGORIES로 병렬 검색하고, verifiable=true인 liked_tags/disliked_tags가
    있으면 태그별 검색도 추가해 title 기준으로 병합한다.

    2026-08-11(2차)부터 지역은 항상 세부지역이 포함된 단일 값이라(NormalizedConditions.
    validate_region) 광역 시/도 확장(app.services.regions, 삭제됨)은 더 이상
    필요 없다 — 카테고리·태그 쿼리 팬아웃만으로 지역당 최소 50개 이상의 고유
    장소를 모으는 게 목표.

    쏘기 전에 일일 호출 예산(app/services/rate_limiter.reserve_daily_budget)을
    먼저 확보한다 — 부족하면 뒤쪽(태그 쿼리부터)이 잘려서 확보되는 만큼만
    검색되고, place_candidates가 그만큼 적은 채로 파이프라인이 계속 진행된다.

    session_id는 orchestrate.generate_schedule_candidates()가 요청마다 이미
    만들어 쓰는 값을 그대로 넘겨받는다 — rate_limiter의 라운드로빈이 이 값으로
    "어느 요청에서 나온 호출들인지" 묶어서 다른 요청과 공평하게 나눠 갖는다.
    """
    started = time.perf_counter()
    queries = _build_queries(region, liked_tags or [], disliked_tags or [])
    granted = await reserve_daily_budget(
        "naver_search", len(queries), settings.naver_daily_call_limit
    )
    queries = queries[:granted]
    if not queries:
        return PlaceSearchResult(
            [],
            {"candidate_count": 0, "groups": {"liked": [], "disliked": [], "categories": []}},
        )

    results_per_query = await asyncio.gather(
        *(search_places(query, session_id=session_id, sort=sort) for query, _, _, sort in queries),
        return_exceptions=True,
    )
    merged, any_failed = _merge_results(queries, results_per_query)

    # merged가 비어도 "이 지역에 후보가 진짜 없음"과 "호출이 전부 실패해서 못
    # 받아온 것"은 다른 상황이다 — 후자를 빈 리스트로 조용히 돌려주면 호출부가
    # "후보 없음"으로 오해한다. 일부만 실패했을 땐(partial success) 성공한 결과가
    # 있으므로 raise하지 않는다.
    if not merged and any_failed:
        raise NaverSearchError("모든 카테고리·태그 조회가 실패해 병합할 결과가 없습니다.")
    result = PlaceSearchResult(
        list(merged.values()),
        _build_search_groups(queries, results_per_query, set(merged)),
    )
    logger.info(
        "place_search region=%s query_count=%s result_count=%s elapsed_seconds=%.3f",
        region,
        len(queries),
        len(result),
        time.perf_counter() - started,
    )
    return result

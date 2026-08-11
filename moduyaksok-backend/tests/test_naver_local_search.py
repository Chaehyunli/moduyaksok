# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : search_places() 테스트. httpx.AsyncClient를 mock —
#              네이버가 실제로 뭘 돌려주는지가 아니라 우리 호출/파싱 로직을 검증한다.
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
import httpx
import pytest

from app.services.naver_local_search import (
    NaverSearchError,
    search_places,
    search_places_for_region,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://naverapihub.apigw.ntruss.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """호출 인자를 captured에 기록하고, response_factory()가 만든 응답을 돌려준다."""

    captured: dict = {}

    def __init__(self, response_factory, *, raise_timeout: bool = False):
        self._response_factory = response_factory
        self._raise_timeout = raise_timeout

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, headers=None, params=None):
        _FakeAsyncClient.captured = {"url": url, "headers": headers, "params": params}
        if self._raise_timeout:
            raise httpx.TimeoutException("timed out")
        return self._response_factory()


def _patch_client(monkeypatch, response_factory=None, *, raise_timeout=False):
    fake = _FakeAsyncClient(response_factory, raise_timeout=raise_timeout)
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)
    return fake


async def test_search_places_parses_items(monkeypatch):
    payload = {
        "items": [{"title": "<b>잠실</b>장어와 한우", "category": "한식", "address": "서울 송파구"}]
    }
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    results = await search_places("잠실 맛집", display=3)

    assert results == [
        {
            "title": "잠실장어와 한우",
            "category": "한식",
            "address": "서울 송파구",
            "description": "",
        }
    ]


async def test_search_places_strips_html_tags_from_title_and_description(monkeypatch):
    payload = {
        "items": [
            {
                "title": "<b>대홍집</b> 잠실새내본점",
                "description": "<b>맛있는</b> 한식당",
                "category": "한식",
            }
        ]
    }
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    results = await search_places("잠실")

    assert results[0]["title"] == "대홍집 잠실새내본점"
    assert results[0]["description"] == "맛있는 한식당"


async def test_search_places_returns_empty_list_when_no_items(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"items": []}))

    results = await search_places("존재하지 않는 지역 검색어")

    assert results == []


async def test_search_places_missing_items_key_returns_empty_list(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {}))

    results = await search_places("아무거나")

    assert results == []


async def test_search_places_raises_naver_search_error_on_4xx(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(401, {}))

    with pytest.raises(NaverSearchError):
        await search_places("아무거나")


async def test_search_places_raises_naver_search_error_on_5xx(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(500, {}))

    with pytest.raises(NaverSearchError):
        await search_places("아무거나")


async def test_search_places_raises_naver_search_error_on_timeout(monkeypatch):
    _patch_client(monkeypatch, raise_timeout=True)

    with pytest.raises(NaverSearchError):
        await search_places("아무거나")


async def test_search_places_sends_client_id_and_secret_headers(monkeypatch):
    monkeypatch.setattr(
        "app.services.naver_local_search.settings.naver_search_client_id", "fake-id"
    )
    monkeypatch.setattr(
        "app.services.naver_local_search.settings.naver_search_client_secret", "fake-secret"
    )
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"items": []}))

    await search_places("아무거나")

    headers = _FakeAsyncClient.captured["headers"]
    assert headers["X-NCP-APIGW-API-KEY-ID"] == "fake-id"
    assert headers["X-NCP-APIGW-API-KEY"] == "fake-secret"


async def test_search_places_caps_display_at_max_five(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"items": []}))

    await search_places("아무거나", display=20)

    assert _FakeAsyncClient.captured["params"]["display"] == 5


class _RecordingFakeAsyncClient:
    """query별로 다른 결과를 돌려주는 fake — region×category 팬아웃 검증용."""

    calls: list[str] = []

    def __init__(self, responses_by_query: dict[str, list[dict]]):
        self._responses = responses_by_query

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, headers=None, params=None):
        query = params["query"]
        _RecordingFakeAsyncClient.calls.append(query)
        items = self._responses.get(query, [])
        return _FakeResponse(200, {"items": items})


async def test_search_places_for_region_dedupes_by_title(monkeypatch):
    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 한식": [{"title": "중복집", "category": "한식", "address": "서울 잠실"}],
            "서울 잠실 카페": [{"title": "중복집", "category": "한식", "address": "서울 잠실"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region("서울 잠실")

    assert len([r for r in results if r["title"] == "중복집"]) == 1


async def test_search_places_for_region_queries_every_category(monkeypatch):
    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient({})
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    await search_places_for_region("서울 잠실")

    from app.services.naver_local_search import _PLACE_CATEGORIES

    for category in _PLACE_CATEGORIES:
        assert f"서울 잠실 {category}" in _RecordingFakeAsyncClient.calls


async def test_search_places_for_region_searches_verifiable_liked_tags_and_marks_matched(
    monkeypatch,
):
    from app.pipeline.schemas import PreferenceTag

    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 와플": [
                {"title": "와플가게", "category": "카페,디저트>와플", "address": "서울 잠실"}
            ]
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region(
        "서울 잠실", liked_tags=[PreferenceTag(tag="와플", verifiable=True)]
    )

    matched = next(r for r in results if r["title"] == "와플가게")
    assert matched["matched_tag"] == "와플"


async def test_search_places_for_region_attaches_source_category(monkeypatch):
    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 한식": [{"title": "잠실집", "category": "한식", "address": "서울 잠실"}],
            "서울 잠실 카페": [{"title": "카페집", "category": "카페", "address": "서울 잠실"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region("서울 잠실")

    by_title = {r["title"]: r for r in results}
    assert by_title["잠실집"]["source_category"] == "한식"
    assert by_title["카페집"]["source_category"] == "카페"


async def test_search_places_for_region_source_category_missing_for_tag_only_match(monkeypatch):
    from app.pipeline.schemas import PreferenceTag

    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 와플": [
                {"title": "와플전문점", "category": "카페,디저트>와플", "address": "서울 잠실"}
            ]
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region(
        "서울 잠실", liked_tags=[PreferenceTag(tag="와플", verifiable=True)]
    )

    matched = next(r for r in results if r["title"] == "와플전문점")
    assert matched.get("source_category") is None


async def test_search_places_for_region_ignores_non_verifiable_liked_tags(monkeypatch):
    from app.pipeline.schemas import PreferenceTag

    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient({})
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    await search_places_for_region(
        "서울 잠실", liked_tags=[PreferenceTag(tag="조용한 분위기", verifiable=False)]
    )

    assert "서울 잠실 조용한 분위기" not in _RecordingFakeAsyncClient.calls


async def test_search_places_for_region_excludes_disliked_tag_matches(monkeypatch):
    from app.pipeline.schemas import PreferenceTag

    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 카페": [
                {"title": "해산물집", "category": "한식", "address": "서울 잠실"},
                {"title": "무난한카페", "category": "카페", "address": "서울 잠실"},
            ],
            "서울 잠실 해산물": [{"title": "해산물집", "category": "한식", "address": "서울 잠실"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region(
        "서울 잠실", disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)]
    )

    titles = {r["title"] for r in results}
    assert "해산물집" not in titles
    assert "무난한카페" in titles


async def test_search_places_for_region_keeps_grouped_search_snapshot(monkeypatch):
    from app.pipeline.schemas import PreferenceTag

    fake = _RecordingFakeAsyncClient(
        {
            "서울 잠실 카페": [
                {"title": "해산물집", "category": "한식", "address": "서울 잠실"},
                {"title": "무난한카페", "category": "카페", "address": "서울 잠실"},
            ],
            "서울 잠실 와플": [{"title": "와플가게", "category": "카페", "address": "서울 잠실"}],
            "서울 잠실 해산물": [{"title": "해산물집", "category": "한식", "address": "서울 잠실"}],
        }
    )
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    results = await search_places_for_region(
        "서울 잠실",
        liked_tags=[PreferenceTag(tag="와플", verifiable=True)],
        disliked_tags=[PreferenceTag(tag="해산물", verifiable=True)],
    )

    snapshot = results.search_groups
    assert snapshot["candidate_count"] == len(results)
    assert snapshot["groups"]["liked"][0]["label"] == "와플"
    assert snapshot["groups"]["liked"][0]["places"][0]["map_url"].startswith(
        "https://map.naver.com"
    )
    assert snapshot["groups"]["disliked"][0]["places"][0]["name"] == "해산물집"
    cafe_group = next(
        group for group in snapshot["groups"]["categories"] if group["label"] == "카페"
    )
    assert [place["name"] for place in cafe_group["places"]] == ["무난한카페"]


async def test_search_places_for_region_caps_verifiable_tags_at_five(monkeypatch):
    from app.pipeline.schemas import PreferenceTag

    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient({})
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    tags = [PreferenceTag(tag=f"태그{i}", verifiable=True) for i in range(7)]
    await search_places_for_region("서울 잠실", liked_tags=tags)

    tag_calls = [c for c in _RecordingFakeAsyncClient.calls if c.startswith("서울 잠실 태그")]
    assert len(tag_calls) == 5


async def test_search_places_for_region_truncates_queries_when_daily_budget_short(monkeypatch):
    # 일일 예산이 부족하면 확보된 만큼만 쿼리를 보내고, 나머지는 조용히 스킵한다
    # (2026-08-11 결정 — 하드 실패보다 place_candidates가 적은 채로 진행하는 쪽).
    _RecordingFakeAsyncClient.calls = []
    fake = _RecordingFakeAsyncClient({})
    monkeypatch.setattr("app.services.naver_local_search.httpx.AsyncClient", fake)

    async def limited_budget(requested: int) -> int:
        return 2

    monkeypatch.setattr("app.services.naver_local_search.reserve_daily_budget", limited_budget)

    results = await search_places_for_region("서울 잠실")

    assert len(_RecordingFakeAsyncClient.calls) == 2
    assert results == []


async def test_search_places_for_region_returns_empty_when_daily_budget_exhausted(monkeypatch):
    async def zero_budget(requested: int) -> int:
        return 0

    monkeypatch.setattr("app.services.naver_local_search.reserve_daily_budget", zero_budget)

    results = await search_places_for_region("서울 잠실")

    assert results == []


async def test_search_places_for_region_raises_when_every_query_fails(monkeypatch):
    # 모든 카테고리 조회가 실패(타임아웃 등)하면 "후보 없음"(빈 리스트)과 구분해서
    # NaverSearchError를 올려야 한다 — 안 그러면 호출부가 "이 지역엔 진짜로 후보가
    # 없다"로 오해한다.
    _patch_client(monkeypatch, raise_timeout=True)

    with pytest.raises(NaverSearchError):
        await search_places_for_region("서울 잠실")


async def test_search_places_for_region_partial_failure_does_not_raise(monkeypatch):
    # 일부 쿼리만 실패했을 땐 성공한 결과가 있으므로 raise하지 않는다.
    async def flaky_search_places(query, display=5, session_id=""):
        if "카페" in query:
            raise NaverSearchError("일부러 실패")
        return [{"title": f"{query} 결과", "category": "한식", "address": "서울"}]

    monkeypatch.setattr("app.services.naver_local_search.search_places", flaky_search_places)

    results = await search_places_for_region("서울 잠실")

    assert len(results) > 0

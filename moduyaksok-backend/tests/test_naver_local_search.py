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

from app.services.naver_local_search import NaverSearchError, search_places


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

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : naver_directions.py 테스트. httpx.AsyncClient를 mock —
#              NCP Maps가 실제로 뭘 돌려주는지가 아니라 우리 호출/파싱/폴백
#              로직을 검증한다(응답 형태는 api.ncloud-docs.com Directions 5
#              레퍼런스 기준 픽스처).
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, _SUCCESS_PAYLOAD에 "path" 필드(NCP가 주는 [lng, lat] 좌표 배열)
#             추가. 새 테스트 2개 추가: 경로 좌표가 (lat, lng) 튜플로 올바르게
#             변환되는지, 경로가 없을 때 빈 리스트로 기본값이 되는지 검증.
# 2026-08-15, 일시적 실패 후 재시도로 성공하는지 검증하는 테스트 추가
#             (naver_directions.py의 같은 날짜 변경사항 참고).
# ------------------------------------------------------------------
import httpx
import pytest

from app.services.naver_directions import NaverDirectionsError, get_car_option

_GANGNAM = (37.497942, 127.027621)
_CITY_HALL = (37.5648, 126.9765)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://maps.apigw.ntruss.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._payload


class _FakeAsyncClient:
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

    async def get(self, url, params=None, headers=None):
        _FakeAsyncClient.captured = {"url": url, "params": params, "headers": headers}
        if self._raise_timeout:
            raise httpx.TimeoutException("timed out")
        return self._response_factory()


def _patch_client(monkeypatch, response_factory=None, *, raise_timeout=False):
    fake = _FakeAsyncClient(response_factory, raise_timeout=raise_timeout)
    monkeypatch.setattr("app.services.naver_directions.httpx.AsyncClient", fake)
    return fake


_SUCCESS_PAYLOAD = {
    "code": 0,
    "route": {
        "trafast": [
            {
                "summary": {
                    "distance": 12000,
                    "duration": 900000,  # ms -> 15분
                    "tollFare": 0,
                    "fuelPrice": 1800,
                },
                # NCP Directions 5는 [경도, 위도] 순서로 좌표 배열을 준다.
                "path": [[127.027621, 37.497942], [127.02, 37.52], [126.9765, 37.5648]],
            }
        ]
    },
}


async def test_get_car_option_parses_duration_and_fare(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _SUCCESS_PAYLOAD))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option is not None
    assert option.option_id == "car"
    assert option.mode == "car"
    assert option.duration_minutes == 15
    assert option.fare_krw == 1800


async def test_get_car_option_returns_none_on_no_route_error_code(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"code": 5, "route": {}}))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option is None


async def test_get_car_option_returns_none_when_no_routes_in_response(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"code": 0, "route": {"trafast": []}}))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option is None


async def test_get_car_option_raises_on_timeout(monkeypatch):
    _patch_client(monkeypatch, raise_timeout=True)

    with pytest.raises(NaverDirectionsError):
        await get_car_option(*_GANGNAM, *_CITY_HALL)


async def test_get_car_option_raises_on_5xx(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(500, {}))

    with pytest.raises(NaverDirectionsError):
        await get_car_option(*_GANGNAM, *_CITY_HALL)


async def test_get_car_option_sends_client_id_secret_headers_and_coordinates(monkeypatch):
    monkeypatch.setattr("app.services.naver_directions.settings.naver_map_client_id", "fake-id")
    monkeypatch.setattr(
        "app.services.naver_directions.settings.naver_map_client_secret", "fake-secret"
    )
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"code": 5, "route": {}}))

    await get_car_option(*_GANGNAM, *_CITY_HALL)

    captured = _FakeAsyncClient.captured
    assert captured["headers"]["x-ncp-apigw-api-key-id"] == "fake-id"
    assert captured["headers"]["x-ncp-apigw-api-key"] == "fake-secret"
    assert captured["params"]["start"] == f"{_GANGNAM[1]},{_GANGNAM[0]}"
    assert captured["params"]["goal"] == f"{_CITY_HALL[1]},{_CITY_HALL[0]}"


async def test_get_car_option_converts_path_to_lat_lng_tuples(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _SUCCESS_PAYLOAD))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option.path == [(37.497942, 127.027621), (37.52, 127.02), (37.5648, 126.9765)]


async def test_get_car_option_retries_once_after_transient_failure(monkeypatch):
    attempts = {"count": 0}

    class _FlakyClient(_FakeAsyncClient):
        async def get(self, url, params=None, headers=None):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise httpx.TimeoutException("timed out")
            return _FakeResponse(200, _SUCCESS_PAYLOAD)

    monkeypatch.setattr(
        "app.services.naver_directions.httpx.AsyncClient", _FlakyClient(lambda: None)
    )

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option is not None
    assert attempts["count"] == 2


async def test_get_car_option_path_defaults_to_empty_list_when_missing(monkeypatch):
    payload = {
        "code": 0,
        "route": {"trafast": [{"summary": _SUCCESS_PAYLOAD["route"]["trafast"][0]["summary"]}]},
    }
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    option = await get_car_option(*_GANGNAM, *_CITY_HALL)

    assert option.path == []

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : odsay_directions.py 테스트. httpx.AsyncClient를 mock —
#              ODsay가 실제로 뭘 돌려주는지가 아니라 우리 호출/파싱/폴백 로직을
#              검증한다(700m 폴백은 lab.odsay.com 실측으로 확인한 -98 응답 형태를
#              그대로 픽스처로 씀).
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, get_transit_option(단수, paths[0]만) -> get_transit_options(복수)로
#             바뀐 데 맞춰 전체 재작성 — 여러 경로가 왔을 때 전부 반환하는지,
#             option_id/transfer_count/description이 올바른지 검증 추가.
# 2026-08-10, 대중교통 경로 폴리라인 테스트 3개 추가. subPath[]에서 좌표 있는
#             구간만 이어붙이는지, 좌표 없는 구간은 건너뛰는지, subPath 자체가
#             없는 응답도 처리하는지 검증.
# ------------------------------------------------------------------
import httpx
import pytest

from app.services.odsay_directions import OdsayError, get_transit_options, get_walk_option

_GANGNAM = (37.497942, 127.027621)
_CITY_HALL = (37.5648, 126.9765)
_NEARBY = (37.4985, 127.0280)  # 강남역에서 700m 이내


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.odsay.com")
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
    monkeypatch.setattr("app.services.odsay_directions.httpx.AsyncClient", fake)
    return fake


def test_get_walk_option_needs_no_network_call():
    option = get_walk_option(*_GANGNAM, *_CITY_HALL)

    assert option.option_id == "walk"
    assert option.mode == "walk"
    assert option.fare_krw == 0
    assert option.duration_minutes > 0


_TWO_PATH_PAYLOAD = {
    "result": {
        "path": [
            {
                "pathType": 1,
                "info": {
                    "totalTime": 39,
                    "payment": 1650,
                    "busTransitCount": 0,
                    "subwayTransitCount": 3,
                    "firstStartStation": "강남",
                    "lastEndStation": "시청",
                },
            },
            {
                "pathType": 2,
                "info": {
                    "totalTime": 55,
                    "payment": 1300,
                    "busTransitCount": 1,
                    "subwayTransitCount": 0,
                    "firstStartStation": "강남",
                    "lastEndStation": "시청",
                },
            },
        ]
    }
}


async def test_get_transit_options_returns_every_path_not_just_first(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert len(options) == 2
    assert [o.duration_minutes for o in options] == [39, 55]
    assert [o.fare_krw for o in options] == [1650, 1300]


async def test_get_transit_options_assigns_unique_option_ids(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert [o.option_id for o in options] == ["transit-0", "transit-1"]


async def test_get_transit_options_builds_description_from_path_type_and_stations(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].description == "지하철 강남 → 시청"
    assert options[1].description == "버스 강남 → 시청"


async def test_get_transit_options_derives_transfer_count_from_transit_legs(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    # subwayTransitCount=3 -> 3개 구간 탑승 -> 환승 2번
    assert options[0].transfer_count == 2
    # busTransitCount=1 -> 1개 구간 탑승 -> 환승 0번
    assert options[1].transfer_count == 0


async def test_get_transit_options_returns_empty_list_for_close_coords_without_calling_api(
    monkeypatch,
):
    # 700m 이내면 haversine으로 미리 걸러서 API를 아예 안 부른다.
    _patch_client(monkeypatch, lambda: (_ for _ in ()).throw(AssertionError("호출되면 안 됨")))

    options = await get_transit_options(*_GANGNAM, *_NEARBY)

    assert options == []


async def test_get_transit_options_returns_empty_list_on_too_close_error_response(monkeypatch):
    payload = {"error": {"msg": "출, 도착지가 700m이내입니다.", "code": "-98"}}
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options == []


async def test_get_transit_options_returns_empty_list_when_no_path_found(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"result": {"path": []}}))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options == []


async def test_get_transit_options_raises_odsay_error_on_timeout(monkeypatch):
    _patch_client(monkeypatch, raise_timeout=True)

    with pytest.raises(OdsayError):
        await get_transit_options(*_GANGNAM, *_CITY_HALL)


async def test_get_transit_options_raises_odsay_error_on_5xx(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(500, {}))

    with pytest.raises(OdsayError):
        await get_transit_options(*_GANGNAM, *_CITY_HALL)


async def test_get_transit_options_sends_referer_header_and_coordinates(monkeypatch):
    monkeypatch.setattr("app.services.odsay_directions.settings.odsay_api_key", "fake-key")
    monkeypatch.setattr(
        "app.services.odsay_directions.settings.odsay_referer_url", "localhost:8000"
    )
    _patch_client(monkeypatch, lambda: _FakeResponse(200, {"result": {"path": []}}))

    await get_transit_options(*_GANGNAM, *_CITY_HALL)

    captured = _FakeAsyncClient.captured
    assert captured["headers"]["Referer"] == "localhost:8000"
    assert captured["params"]["apiKey"] == "fake-key"
    assert captured["params"]["SY"] == _GANGNAM[0]
    assert captured["params"]["SX"] == _GANGNAM[1]


_PATH_WITH_SUBPATH = {
    "result": {
        "path": [
            {
                "pathType": 1,
                "info": {
                    "totalTime": 39,
                    "payment": 1650,
                    "busTransitCount": 0,
                    "subwayTransitCount": 3,
                    "firstStartStation": "강남",
                    "lastEndStation": "시청",
                },
                # scripts/odsay_route_check.md 실측 응답 구조 그대로 — trafficType=3(도보)엔
                # 좌표가 없고, 1(지하철)엔 startX/Y·endX/Y가 있다.
                "subPath": [
                    {"trafficType": 3, "distance": 1, "sectionTime": 1},
                    {
                        "trafficType": 1,
                        "distance": 1200,
                        "sectionTime": 2,
                        "startX": 127.027618,
                        "startY": 37.497949,
                        "endX": 127.014394,
                        "endY": 37.493902,
                    },
                    {"trafficType": 3, "distance": 0, "sectionTime": 2},
                    {
                        "trafficType": 1,
                        "distance": 11200,
                        "sectionTime": 19,
                        "startX": 127.014394,
                        "startY": 37.493902,
                        "endX": 126.9765,
                        "endY": 37.5648,
                    },
                ],
            }
        ]
    }
}


async def test_get_transit_options_builds_path_from_non_walk_subpaths(monkeypatch):
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _PATH_WITH_SUBPATH))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == [
        (37.497949, 127.027618),
        (37.493902, 127.014394),
        (37.493902, 127.014394),
        (37.5648, 126.9765),
    ]


async def test_get_transit_options_path_empty_when_subpath_missing(monkeypatch):
    # _TWO_PATH_PAYLOAD(기존 픽스처)엔 subPath가 아예 없다 — 그런 응답도 있을 수
    # 있으니 깨지지 않고 빈 리스트를 줘야 한다.
    _patch_client(monkeypatch, lambda: _FakeResponse(200, _TWO_PATH_PAYLOAD))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == []


async def test_get_transit_options_skips_subpath_leg_missing_coords(monkeypatch):
    payload = {
        "result": {
            "path": [
                {
                    "pathType": 2,
                    "info": {
                        "totalTime": 20,
                        "payment": 1200,
                        "busTransitCount": 1,
                        "subwayTransitCount": 0,
                        "firstStartStation": "A",
                        "lastEndStation": "B",
                    },
                    "subPath": [
                        {"trafficType": 2, "distance": 100, "sectionTime": 3},  # 좌표 없음
                    ],
                }
            ]
        }
    }
    _patch_client(monkeypatch, lambda: _FakeResponse(200, payload))

    options = await get_transit_options(*_GANGNAM, *_CITY_HALL)

    assert options[0].path == []

# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step4가 쓸 이동 옵션 조회. 도보는 좌표 기반 직선거리 추정(API 호출
#              없음), 대중교통은 ODsay(lab.odsay.com) searchPubTransPathT 호출.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. 실측(스크립트로 직접 호출, docs/AI파이프라인_Step별_설계
#             Step4 절 참고) 결과:
#             - mapx/mapy는 WGS84 경도/위도 × 10^7이라 변환 불필요.
#             - searchPubTransPathT는 출발 시각 파라미터가 없다(정적 그래프 탐색) —
#               막차/첫차 여부는 이 API로 확인 불가, 시스템이 확인 안 하기로 함.
#             - 출발/도착이 700m 이내면 error.code="-98"을 반환 — 이 경우 대중교통
#               옵션 없이 도보만 제공한다(ODsay 정책이자 상식적으로도 그 거리는
#               대중교통보다 도보가 합리적).
#             - 서비스 플랫폼을 URI로 등록해서, 호출 시 Referer 헤더를 등록한 값과
#               맞춰야 인증이 통과된다(브라우저가 아니라 서버 대 서버 호출이라
#               자동으로 안 붙는다 — settings.odsay_referer_url을 직접 세팅).
# 2026-08-10, get_transit_option()(단수, paths[0]만 사용) -> get_transit_options()
#             (복수)로 변경. scripts/verify_odsay_routes.py로 실측해보니 ODsay가
#             한 응답에 지하철만/버스만/환승조합 등 여러 경로를 같이 주는데
#             paths[0](추천 1순위)만 쓰고 나머지를 버리고 있었음 — "조회된 모든
#             방법을 다 보여주고 사용자가 고른다"는 요구사항과 안 맞아서 정정.
# 2026-08-10, 대중교통 경로에 구간별 좌표(polyline) 추가. subPath[]의 각 항목
#             (trafficType 1=지하철, 2=버스, 3=도보)에서 trafficType=3인 구간은
#             좌표가 없어 건너뛰고, 나머지의 startX/Y·endX/Y를 순서대로 이어붙여
#             RouteOption.path(lat, lng 튜플 리스트)로 채운다.
# 2026-08-15, 사용자가 "백 로그를 보니 경로 찾기 실패가 많다"고 리포트했는데,
#             지금까진 700m 이내 스킵도 ODsay가 준 그 외 에러(인증 실패·일시 장애
#             등 진짜 실패 포함)도 전부 로그 없이 조용히 빈 리스트로 삼켜서 로그만
#             보고는 "정상 무경로"와 "진짜 실패"를 구분할 방법이 아예 없었다.
#             ① 클라이언트 사이드 700m 사전 체크와 ② API가 준 error.code="-98"
#             (ODsay 자체 판단 700m 이내) 둘 다 info로 남기고, ③ 그 외 에러
#             코드는 warning으로 code/message를 남겨 다음부터는 로그만으로 원인을
#             구분할 수 있게 했다 — 사용자 경험(빈 옵션으로 degrade)은 그대로 유지.
#             네트워크 hiccup 한 번에 그 구간 옵션이 통째로 사라지는 문제도 같이
#             확인돼 짧은 재시도(1회, 백오프 없음)를 추가했다.
# 2026-08-15(2차), get_walk_option()이 estimate_buffer_minutes() 대신
#             estimate_walk_minutes()를 쓰도록 수정 — 사용자가 "도보 시간
#             측정이 잘못된 것 같다"고 리포트. 원인: estimate_buffer_minutes()는
#             거리가 1km 넘으면 대중교통(18km/h)/자차(42km/h) 속도로 전환되는데,
#             "도보" 옵션에 그대로 재사용해서 먼 구간일수록 실제 도보(4.5km/h)
#             보다 훨씬 짧은 시간이 표시됐다(travel_estimate.py 참고).
# ------------------------------------------------------------------
import logging

import httpx

from app.config import settings
from app.pipeline.schemas import RouteOption
from app.pipeline.travel_estimate import estimate_walk_minutes, haversine_distance_m

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"

# 700m 이내면 ODsay가 대중교통 검색 자체를 거부한다(error.code="-98", 실측 확인).
_TOO_CLOSE_ERROR_CODE = "-98"

# 일시적 네트워크 hiccup 한 번으로 그 구간의 대중교통 옵션이 통째로 사라지는 걸
# 막기 위한 재시도 횟수(백오프 없이 즉시 재시도) — ponytail: 더 정교한 지수
# 백오프는 실제로 1회 재시도로 부족하다는 게 실측되면 그때 추가.
_MAX_ATTEMPTS = 2

# ODsay의 pathType 값 — 공식 문서 기준 1=지하철, 2=버스, 3=지하철+버스 조합.
_PATH_TYPE_LABELS = {1: "지하철", 2: "버스", 3: "버스+지하철"}


class OdsayError(Exception):
    """ODsay 호출 자체가 실패(네트워크 오류, 인증 실패, 5xx 등). "이 구간엔 대중교통
    경로가 없음"(정상적인 빈 결과)과는 구분한다 — 후자는 예외를 던지지 않는다.
    """


def get_walk_option(lat1: float, lng1: float, lat2: float, lng2: float) -> RouteOption:
    """도보 옵션은 API 호출 없이 항상 계산 가능 — 직선거리 기반 추정
    (travel_estimate.estimate_walk_minutes)을 쓴다. 요금은 0원.

    2026-08-15, Step2 버퍼 추정용 estimate_buffer_minutes()를 쓰던 걸 도보 전용
    함수로 교체 — 그 함수는 거리가 1km를 넘으면 대중교통/자차 속도로 전환되므로,
    "도보" 라벨이 붙은 이 옵션에 그대로 쓰면 먼 구간에서 실제보다 훨씬 짧은
    시간이 나온다(사용자 리포트).
    """
    return RouteOption(
        option_id="walk",
        mode="walk",
        duration_minutes=estimate_walk_minutes(lat1, lng1, lat2, lng2),
        fare_krw=0,
    )


def _describe_path(path: dict) -> str:
    info = path.get("info", {})
    label = _PATH_TYPE_LABELS.get(path.get("pathType"), "대중교통")
    start = info.get("firstStartStation", "")
    end = info.get("lastEndStation", "")
    return f"{label} {start} → {end}" if start and end else label


def _transfer_count(info: dict) -> int:
    # ODsay 응답엔 "환승 횟수" 필드가 따로 없어서, 버스+지하철 구간 수를 다 더한
    # 값(총 대중교통 탑승 횟수)에서 1을 빼서 근사한다(탑승 횟수 - 1 = 환승 횟수).
    legs = info.get("busTransitCount", 0) + info.get("subwayTransitCount", 0)
    return max(0, legs - 1)


def _path_from_subpaths(subpaths: list[dict]) -> list[tuple[float, float]]:
    """trafficType=3(도보로 역까지 이동하는 짧은 구간)엔 좌표가 없어 건너뛴다.
    나머지 구간(지하철·버스)의 시작/끝 좌표를 순서대로 이어붙인다 — 완전한 곡선은
    아니지만 두 지점 직선보다 실제 경로에 가깝다(scripts/odsay_route_check.md
    실측 응답 구조 기준).
    """
    points: list[tuple[float, float]] = []
    for leg in subpaths:
        if leg.get("trafficType") == 3:
            continue
        start_x, start_y = leg.get("startX"), leg.get("startY")
        end_x, end_y = leg.get("endX"), leg.get("endY")
        if start_x is None or start_y is None or end_x is None or end_y is None:
            continue
        points.append((float(start_y), float(start_x)))
        points.append((float(end_y), float(end_x)))
    return points


async def get_transit_options(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> list[RouteOption]:
    """대중교통 옵션을 ODsay로 조회한다. ODsay가 한 응답에 여러 경로(지하철만/
    버스만/환승조합)를 같이 주므로, 하나만 고르지 않고 전부 RouteOption으로 변환해
    돌려준다. 700m 이내(-98)거나 경로가 없으면 빈 리스트를 반환한다(정상 상황 —
    호출부가 이 경우 도보만 options에 담는다). 네트워크·인증 실패 등 호출 자체의
    문제는 OdsayError로 올린다.
    """
    if haversine_distance_m(lat1, lng1, lat2, lng2) < 700:
        logger.info(
            "transit_skip_too_close lat1=%s lng1=%s lat2=%s lng2=%s", lat1, lng1, lat2, lng2
        )
        return []

    params = {
        "apiKey": settings.odsay_api_key,
        "SX": lng1,
        "SY": lat1,
        "EX": lng2,
        "EY": lat2,
        "OPT": 0,
        "output": "json",
    }
    headers = {"Referer": settings.odsay_referer_url}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_SEARCH_URL, params=params, headers=headers)
                response.raise_for_status()
            break
        except httpx.HTTPError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise OdsayError(f"ODsay 대중교통 경로 조회 실패: {exc}") from exc

    body = response.json()
    error = body.get("error")
    if error is not None:
        # "이 구간엔 대중교통이 없다"는 정상 결과로 취급해 빈 리스트로 degrade하는
        # 건 그대로 유지한다(호출부가 이 경우 도보만 options에 담는다). 다만
        # 진짜 실패(인증 오류·일시 장애 등)와 정상적인 700m 이내 무경로를 로그에서
        # 구분할 수 있게 code/message를 남긴다 — 예전엔 여기서 아무 로그도 안
        # 남아서 "실패가 잦다"는 걸 로그만으로 확인할 방법이 없었다.
        code = error.get("code") if isinstance(error, dict) else None
        if code == _TOO_CLOSE_ERROR_CODE:
            logger.info("transit_no_route_too_close lat1=%s lng1=%s lat2=%s lng2=%s", lat1, lng1, lat2, lng2)
        else:
            logger.warning("transit_no_route_error code=%s error=%s", code, error)
        return []

    paths = body.get("result", {}).get("path", [])
    options = []
    for i, path in enumerate(paths):
        info = path.get("info", {})
        options.append(
            RouteOption(
                option_id=f"transit-{i}",
                mode="transit",
                duration_minutes=int(info["totalTime"]),
                fare_krw=int(info["payment"]),
                transfer_count=_transfer_count(info),
                description=_describe_path(path),
                path=_path_from_subpaths(path.get("subPath", [])),
            )
        )
    return options

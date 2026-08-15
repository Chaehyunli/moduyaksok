# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step4가 쓸 자차 옵션 조회. NCP Maps Directions 5
#              (maps.apigw.ntruss.com) 호출.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. NCP Maps 콘솔에서 신규 이용 신청이 실제로 열려 있는 걸
#             확인해 채택(문서상 공지로는 "신규 신청 차단"이었으나 콘솔 화면이
#             1차 증거 — 실측 우선). option="trafast"(실시간 빠른길) 1개만
#             조회한다 — 대중교통처럼 여러 대안을 보여줄 만큼 자차 경로 간
#             차이가 크지 않다고 판단, ODsay처럼 여러 옵션을 다 담을 필요 없음.
#             요청 헤더에 Client ID+Secret을 그대로 실어 보내는 것 자체가
#             인증이라(ODsay와 달리 Referer 불필요) settings에서 바로 읽는다.
# 2026-08-10, 도메인을 naveropenapi.apigw.ntruss.com -> maps.apigw.ntruss.com으로
#             수정. 실제 호출에서 errorCode 210 "구독 필요"가 계속 나서 NCP
#             공식 문의로 접수했더니, 콘솔의 "Maps"(VPC) Application은 레거시
#             "AI·NAVER API" 게이트웨이 도메인이 아니라 이 도메인을 써야 한다는
#             답변을 받음 — 여러 블로그·문서가 레거시 도메인만 보여줘서 실측 없이
#             그대로 따라간 게 원인. 수정 후 실제 키로 200 확인.
# 2026-08-10, get_car_option()에 경로 좌표(polyline) 파싱 추가. API가 [lng, lat]
#             쌍으로 주는 좌표 배열을 (lat, lng) 튜플 리스트로 변환해서 반환 —
#             프런트 Naver Maps JS SDK가 LatLng(lat, lng) 순서를 쓰므로 백엔드에서
#             미리 맞춰 보낸다. path가 없으면(도보 옵션 등) 빈 리스트 기본값.
# 2026-08-15, 일시적 네트워크 hiccup 한 번으로 그 구간의 자차 옵션이 통째로
#             사라지는 문제(사용자 리포트)를 확인 — 재시도 없이 1회 실패로 바로
#             NaverDirectionsError를 올리고 있었다. 짧은 재시도(1회, 백오프 없음)
#             추가. odsay_directions.py와 같은 조치.
# ------------------------------------------------------------------
import httpx

from app.config import settings
from app.pipeline.schemas import RouteOption

_DIRECTIONS_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"

# code=0이 성공. 그 외(출발/도착 동일, 도로 주변 아님, 직선거리 1500km 이상 등)는
# "이 구간엔 자차 경로가 없다"는 정상 상황으로 취급한다(공식 API 레퍼런스 기준).
_SUCCESS_CODE = 0

# odsay_directions.py와 같은 이유로 짧은 재시도(백오프 없이 즉시) 1회 추가.
_MAX_ATTEMPTS = 2


class NaverDirectionsError(Exception):
    """NCP Maps Directions 5 호출 자체가 실패(네트워크 오류, 인증 실패, 5xx 등).
    "이 구간엔 자차 경로가 없음"(정상적인 빈 결과)과는 구분한다.
    """


async def get_car_option(lat1: float, lng1: float, lat2: float, lng2: float) -> RouteOption | None:
    """자차 옵션을 NCP Maps Directions 5로 조회한다. 경로를 못 찾으면(code != 0)
    None을 반환한다(호출부가 도보·대중교통만 보여줌). 네트워크·인증 실패 등
    호출 자체의 문제는 NaverDirectionsError로 올린다.
    """
    params = {
        "start": f"{lng1},{lat1}",
        "goal": f"{lng2},{lat2}",
        "option": "trafast",
    }
    headers = {
        "x-ncp-apigw-api-key-id": settings.naver_map_client_id,
        "x-ncp-apigw-api-key": settings.naver_map_client_secret,
    }
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_DIRECTIONS_URL, params=params, headers=headers)
                response.raise_for_status()
            break
        except httpx.HTTPError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise NaverDirectionsError(f"NCP Maps 자차 경로 조회 실패: {exc}") from exc

    body = response.json()
    if body.get("code") != _SUCCESS_CODE:
        return None

    routes = body.get("route", {}).get("trafast", [])
    if not routes:
        return None

    route = routes[0]
    summary = route["summary"]
    # NCP가 주는 [경도, 위도] 쌍을 (위도, 경도)로 뒤집는다 — 프런트 지도 SDK(Naver
    # Maps JS)가 LatLng(lat, lng) 순서를 쓰므로 백엔드에서 미리 맞춰 보낸다.
    path = [(lat, lng) for lng, lat in route.get("path", [])]
    return RouteOption(
        option_id="car",
        mode="car",
        duration_minutes=round(summary["duration"] / 1000 / 60),
        fare_krw=summary.get("tollFare", 0) + summary.get("fuelPrice", 0),
        description="자동차(실시간 빠른길)",
        path=path,
    )

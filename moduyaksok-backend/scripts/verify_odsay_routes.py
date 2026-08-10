# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : app/services/odsay_directions.py(get_walk_option/get_transit_options)가
#              실제 좌표쌍에 대해 어떤 입력을 ODsay에 보내고 어떤 출력을 돌려주는지
#              수동으로 확인하는 스크립트. pytest가 수집하는 tests/ 밖에 있어서
#              평소 테스트 실행에는 안 걸리고, 필요할 때 직접 실행한다. 우리 함수가
#              파싱한 최종 결과(RouteOption)뿐 아니라 ODsay가 실제로 준 원본 JSON도
#              같이 남겨서, 파싱 로직이 원본 응답을 제대로 반영하는지 눈으로 볼 수
#              있게 한다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, get_transit_option(단수, paths[0]만) -> get_transit_options(복수)로
#             바뀐 데 맞춰 갱신 — ODsay가 준 대중교통 경로를 전부 리스트로 보여준다.
#
# 실행: cd moduyaksok-backend && source .venv/bin/activate && python scripts/verify_odsay_routes.py
# 결과: scripts/odsay_route_check.md 를 매번 덮어쓴다 (git으로 마지막 확인 시점 추적).
# 전제: .env에 ODSAY_API_KEY/ODSAY_REFERER_URL이 채워져 있어야 하고, 등록한 서비스
#      URI(ODSAY_REFERER_URL)와 지금 실행 환경이 일치해야 인증이 통과된다.
# ------------------------------------------------------------------
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings
from app.services.odsay_directions import _SEARCH_URL, get_transit_options, get_walk_option

_OUTPUT_PATH = Path(__file__).resolve().parent / "odsay_route_check.md"

# (라벨, 위도, 경도) — 위경도는 실제 검색으로 확인된 값(강남역/서울시청은 mapx/mapy
# 좌표계 실측 때 썼던 것과 동일).
_CASES: list[tuple[str, tuple[float, float, float], tuple[float, float, float]]] = [
    (
        "강남역 -> 서울시청 (충분히 먼 거리, 대중교통 기대)",
        ("강남역", 37.497942, 127.027621),
        ("서울시청", 37.5648, 126.9765),
    ),
    (
        "강남역 -> 강남역 근처(700m 이내, 도보만 기대)",
        ("강남역", 37.497942, 127.027621),
        ("근처 지점", 37.4985, 127.0280),
    ),
    (
        "홍대입구역 -> 합정역 (중간 거리)",
        ("홍대입구역", 37.557527, 126.925784),
        ("합정역", 37.549907, 126.914625),
    ),
]


async def _raw_odsay_response(lat1: float, lng1: float, lat2: float, lng2: float) -> dict:
    """get_transit_options()이 내부적으로 보내는 것과 동일한 요청을 그대로 재현해서,
    파싱 전 원본 JSON을 그대로 남긴다(파싱 로직이 뭘 골라내는지 대조해볼 수 있게).
    """
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
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_SEARCH_URL, params=params, headers=headers)
    # apiKey는 리포트가 git에 커밋되므로 마스킹 — 어떤 파라미터를 보냈는지는
    # 알아야 하니 값 자체만 가린다.
    masked_params = {**params, "apiKey": "***"}
    return {"request_params": masked_params, "status_code": resp.status_code, "body": resp.json()}


def _route_option_to_dict(option) -> dict:
    return {
        "option_id": option.option_id,
        "mode": option.mode,
        "duration_minutes": option.duration_minutes,
        "fare_krw": option.fare_krw,
        "transfer_count": option.transfer_count,
        "description": option.description,
    }


async def _check_case(
    label: str, a: tuple[str, float, float], b: tuple[str, float, float]
) -> list[str]:
    a_name, a_lat, a_lng = a
    b_name, b_lat, b_lng = b

    walk = get_walk_option(a_lat, a_lng, b_lat, b_lng)
    transit_options = await get_transit_options(a_lat, a_lng, b_lat, b_lng)
    raw = await _raw_odsay_response(a_lat, a_lng, b_lat, b_lng)

    parsed = {
        "get_walk_option": _route_option_to_dict(walk),
        "get_transit_options": (
            [_route_option_to_dict(o) for o in transit_options] if transit_options else "없음"
        ),
    }

    lines = [
        f"## {label}",
        "",
        f"- 입력 좌표: {a_name}({a_lat}, {a_lng}) -> {b_name}({b_lat}, {b_lng})",
        f"- 대중교통 옵션 {len(transit_options)}개 조회됨",
        "",
        "### 우리 함수가 파싱한 결과 (조회된 대중교통 옵션 전부)",
        "",
        "```json",
        json.dumps(parsed, ensure_ascii=False, indent=2),
        "```",
        "",
        "### ODsay 원본 응답(get_transit_options이 호출하는 것과 동일 요청)",
        "",
        "```json",
        json.dumps(raw, ensure_ascii=False, indent=2)[:3000],
        "```",
        "",
    ]
    return lines


async def main() -> None:
    lines = [
        "# ODsay 이동 옵션 수동 검증 결과",
        "",
        f"마지막 실행: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "`scripts/verify_odsay_routes.py` 실행 결과 — `app/services/odsay_directions.py`의 "
        "`get_walk_option()`/`get_transit_options()`이 실제로 어떤 값을 돌려주는지, "
        "ODsay 원본 응답과 대조해서 확인한다.",
        "",
    ]
    for label, a, b in _CASES:
        lines.extend(await _check_case(label, a, b))

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"결과를 {_OUTPUT_PATH}에 썼습니다.")


if __name__ == "__main__":
    asyncio.run(main())

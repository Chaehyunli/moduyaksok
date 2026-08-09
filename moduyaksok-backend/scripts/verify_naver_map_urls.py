# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : build_naver_map_url()로 만든 URL이 실제로 네트워크상 살아있는지
#              수동으로 재확인하는 스크립트. pytest가 수집하는 tests/ 밖에 있어서
#              평소 테스트 실행에는 안 걸리고, 필요할 때 직접 실행한다.
#              (map.naver.com은 SPA라 HTTP 200이 "그 장소가 검색 결과에 실제로
#              뜬다"는 걸 보장하진 않음 — "URL이 죽지 않았다/404가 아니다" 수준의
#              확인. 완전한 검증은 헤드리스 브라우저가 필요한데 이 용도로는 과함)
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# 실행: cd moduyaksok-backend && .venv/Scripts/python.exe scripts/verify_naver_map_urls.py
# 결과: scripts/naver_map_url_check.md 를 매번 덮어쓴다 (git으로 마지막 확인 시점 추적).
# ------------------------------------------------------------------
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.services.naver_local_search import search_places_for_regions
from app.services.naver_map_url import build_naver_map_url

_REGIONS = ["서울", "서울 잠실", "경기도 수원"]
_SAMPLES_PER_REGION = 3
_OUTPUT_PATH = Path(__file__).resolve().parent / "naver_map_url_check.md"


async def _check_region(region: str) -> list[dict]:
    places = await search_places_for_regions([region])
    sample = places[:_SAMPLES_PER_REGION]
    results = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for place in sample:
            url = build_naver_map_url(place)
            try:
                resp = await client.get(url)
                status: str = str(resp.status_code)
            except Exception as exc:  # noqa: BLE001 — 수동 점검 스크립트, 원인 그대로 기록
                status = f"ERROR: {exc}"
            results.append(
                {
                    "title": place.get("title", ""),
                    "address": place.get("roadAddress") or place.get("address", ""),
                    "url": url,
                    "status": status,
                }
            )
    return results


async def main() -> None:
    lines = [
        "# 네이버 지도 URL 수동 검증 결과",
        "",
        f"마지막 실행: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "`scripts/verify_naver_map_urls.py` 실행 결과 — HTTP 상태코드만 확인(200이면 "
        "URL이 살아있다는 뜻, 그 장소가 검색 결과에 실제로 뜨는지는 별도 수동 확인 필요).",
        "",
    ]
    for region in _REGIONS:
        lines.append(f"## 지역: {region}")
        lines.append("")
        results = await _check_region(region)
        lines.append(f"결과 {len(results)}개 샘플 확인")
        lines.append("")
        lines.append("| 장소 | 주소 | 상태 | URL |")
        lines.append("|---|---|---|---|")
        for r in results:
            lines.append(f"| {r['title']} | {r['address']} | {r['status']} | {r['url']} |")
        lines.append("")

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"결과를 {_OUTPUT_PATH}에 썼습니다.")


if __name__ == "__main__":
    asyncio.run(main())

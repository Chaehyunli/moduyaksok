# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step1→2→3 전체 파이프라인(+ 관점별 재생성 재시도, orchestrate.py)이
#              실제로 얼마나 걸리는지 재는 스크립트. 실제 네이버 지역검색·LLM
#              호출을 그대로 쓴다(mock 없음) — "일정 하나를 짜기 위해서 드는
#              시간"을 추정이 아니라 실측으로 확인하는 게 목적.
#              재시도 없는 케이스와 있는 케이스를 나눠서 같이 보여준다. 재시도
#              케이스는 LLM이 우연히 실수하길 기다리는 방식(재현 안 됨) 대신,
#              Step2가 실제로 만든 후보 중 하나의 활동 좌표를 스크립트가 직접
#              None으로 지워서 Step3의 규칙 기반 하드 위반(장소 환각)을
#              결정론적으로 강제한다 — LLM 호출 자체(관점 3개 생성/재생성/검증
#              2회)는 전부 진짜라서 시간 측정이 왜곡되지 않는다.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# 실행: cd moduyaksok-backend && source .venv/bin/activate
#      && python scripts/measure_pipeline_timing.py
# 결과: scripts/pipeline_timing_check.md 를 매번 덮어쓴다.
# 전제: .env에 DEEPEVAL_UPSTAGE_API_KEY(또는 실제 BYOK 키)와
#      NAVER_SEARCH_CLIENT_ID/SECRET이 채워져 있어야 한다. 별도 BYOK 키가 없어서
#      DeepEval 전용으로 관리하는 키를 재사용했다 — tests/eval/의 자동 채점에는
#      안 쓰이니 이 스크립트에서 쓰는 건 무방하다.
# ------------------------------------------------------------------
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.pipeline.generate_step2 import (
    generate_candidates_with_perspectives,
    generate_single_candidate,
)
from app.pipeline.normalize_step1 import normalize_conditions
from app.pipeline.schemas import (
    CandidateDraft,
    InfeasibleResponse,
    NormalizedConditions,
    ScheduleResponse,
)
from app.pipeline.synthesize_step3 import synthesize_and_validate
from app.services.naver_local_search import search_places_for_regions

_OUTPUT_PATH = Path(__file__).resolve().parent / "pipeline_timing_check.md"

_PROVIDER = "upstage"
_API_KEY = settings.deepeval_upstage_api_key

_RAW_INPUT = {
    "purpose": "date",
    "headcount": 2,
    "time_range": ["2026-08-15T10:00:00", "2026-08-15T21:00:00"],
    "regions": ["서울 강남"],
    "liked_text": "카페나 맛집 위주로, 조용한 곳이 좋아요",
    "disliked_text": "해산물은 못 먹어요",
    "budget_per_person": 50000,
}


class _Timer:
    """with 블록으로 감싼 구간의 소요시간(초)을 records에 쌓는다."""

    def __init__(self, records: list[tuple[str, float]]):
        self._records = records

    def measure(self, label: str):
        return _TimedBlock(label, self._records)


class _TimedBlock:
    def __init__(self, label: str, records: list[tuple[str, float]]):
        self._label = label
        self._records = records
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info):
        self._records.append((self._label, time.perf_counter() - self._start))
        return False


def _result_summary(result: ScheduleResponse | InfeasibleResponse) -> str:
    if isinstance(result, InfeasibleResponse):
        return f"InfeasibleResponse (reason: {result.reason})"
    titles = ", ".join(c.title for c in result.candidates)
    return f"ScheduleResponse, 후보 {len(result.candidates)}개 ({titles})"


def _missing_perspectives(
    labeled_drafts: list[tuple[str, CandidateDraft]],
    result: ScheduleResponse | InfeasibleResponse,
) -> list[str]:
    if isinstance(result, InfeasibleResponse):
        return [label for label, _ in labeled_drafts]
    survived_titles = {c.title for c in result.candidates}
    return [label for label, draft in labeled_drafts if draft.title not in survived_titles]


async def _run_without_retry(
    conditions: NormalizedConditions, place_candidates: list[dict], records: list[tuple[str, float]]
) -> ScheduleResponse | InfeasibleResponse:
    timer = _Timer(records)

    with timer.measure("[재시도 없음] Step2 — 후보 생성(관점 3개)"):
        labeled_drafts = await generate_candidates_with_perspectives(
            _PROVIDER, _API_KEY, conditions, place_candidates
        )

    with timer.measure("[재시도 없음] Step3 — 검증·병합"):
        result = synthesize_and_validate(
            _PROVIDER, _API_KEY, "timing-no-retry", conditions, [d for _, d in labeled_drafts]
        )

    return result


async def _run_with_forced_retry(
    conditions: NormalizedConditions, place_candidates: list[dict], records: list[tuple[str, float]]
) -> ScheduleResponse | InfeasibleResponse:
    timer = _Timer(records)

    with timer.measure("[재시도 강제] Step2 — 후보 생성(관점 3개)"):
        labeled_drafts = await generate_candidates_with_perspectives(
            _PROVIDER, _API_KEY, conditions, place_candidates
        )

    # 첫 번째 후보의 첫 활동 좌표를 직접 지워서 장소 환각(하드 위반)을 강제한다 —
    # 규칙 기반 체크라 LLM 운에 기대지 않고 100% 재현된다.
    corrupted_label, corrupted_draft = labeled_drafts[0]
    if corrupted_draft.activities:
        corrupted_activities = list(corrupted_draft.activities)
        corrupted_activities[0] = corrupted_activities[0].model_copy(
            update={"lat": None, "lng": None}
        )
        corrupted_draft = corrupted_draft.model_copy(update={"activities": corrupted_activities})
        labeled_drafts[0] = (corrupted_label, corrupted_draft)

    with timer.measure("[재시도 강제] Step3 — 1차 검증(강제로 1개 드롭됨)"):
        first_result = synthesize_and_validate(
            _PROVIDER, _API_KEY, "timing-retry", conditions, [d for _, d in labeled_drafts]
        )

    missing = _missing_perspectives(labeled_drafts, first_result)

    regenerated: list[CandidateDraft] = []
    for label in missing:
        with timer.measure(f"[재시도 강제] Step2 — 관점 재생성({label})"):
            try:
                regenerated.append(
                    generate_single_candidate(
                        _PROVIDER, _API_KEY, conditions, place_candidates, label
                    )
                )
            except Exception as exc:  # noqa: BLE001 — 측정 스크립트, 실패도 기록만 하고 계속
                print(f"  관점 재생성 실패({label}): {exc}")

    if not regenerated:
        return first_result

    surviving_drafts = [draft for label, draft in labeled_drafts if label not in missing]
    with timer.measure("[재시도 강제] Step3 — 2차 검증(재생성분 포함)"):
        final_result = synthesize_and_validate(
            _PROVIDER,
            _API_KEY,
            "timing-retry",
            conditions,
            surviving_drafts + regenerated,
        )

    return final_result


async def main() -> None:
    lines = [
        "# 파이프라인 소요시간 실측 결과",
        "",
        f"마지막 실행: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "`scripts/measure_pipeline_timing.py` 실행 결과 — Step1→2→3 실제 호출(네이버 "
        '지역검색·LLM 전부 진짜) 소요시간. "재시도 강제" 케이스는 Step2가 만든 후보 '
        "1개의 좌표를 스크립트가 직접 지워서 Step3의 장소 환각 하드 위반을 결정론적으로 "
        "재현한 것 — LLM 운에 기대지 않는다.",
        "",
        "## 사용자 입력 조건",
        "",
        "`POST /schedules` 요청 바디 그대로(가정) — 아래 두 케이스 다 이 조건 하나를 공유한다:",
        "",
        "```json",
        json.dumps(_RAW_INPUT, ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    shared_records: list[tuple[str, float]] = []
    timer = _Timer(shared_records)

    with timer.measure("[공통] 네이버 지역검색 (place_candidates 조회)"):
        place_candidates = await search_places_for_regions(_RAW_INPUT["regions"])

    with timer.measure("[공통] Step1 — 조건 정규화"):
        conditions = normalize_conditions(_PROVIDER, _API_KEY, _RAW_INPUT)

    lines.append(
        "Step1이 liked_text/disliked_text에서 뽑아낸 구조화 조건(`NormalizedConditions`, "
        "나머지 필드는 입력 그대로 통과):"
    )
    lines.append("")
    lines.append("```json")
    lines.append(conditions.model_dump_json(indent=2))
    lines.append("```")
    lines.append("")

    print(f"place_candidates {len(place_candidates)}개, 조건 정규화 완료")

    no_retry_records: list[tuple[str, float]] = []
    no_retry_result = await _run_without_retry(conditions, place_candidates, no_retry_records)

    retry_records: list[tuple[str, float]] = []
    retry_result = await _run_with_forced_retry(conditions, place_candidates, retry_records)

    lines.append("## 공통 준비 단계 (양쪽 케이스가 공유)")
    lines.append("")
    lines.append("| 단계 | 소요시간(초) |")
    lines.append("|---|---|")
    shared_total = 0.0
    for label, seconds in shared_records:
        lines.append(f"| {label} | {seconds:.2f} |")
        shared_total += seconds
    lines.append(f"| **소계** | **{shared_total:.2f}** |")
    lines.append("")

    for title, records, result in [
        ("재시도 없는 케이스", no_retry_records, no_retry_result),
        ("재시도 강제 케이스", retry_records, retry_result),
    ]:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| 단계 | 소요시간(초) |")
        lines.append("|---|---|")
        subtotal = 0.0
        for label, seconds in records:
            lines.append(f"| {label} | {seconds:.2f} |")
            subtotal += seconds
        lines.append(f"| **소계** | **{subtotal:.2f}** |")
        lines.append(f"| **공통 준비 단계 포함 총합** | **{shared_total + subtotal:.2f}** |")
        lines.append("")
        lines.append(f"결과: {_result_summary(result)}")
        lines.append("")
        lines.append(
            "실제 생성된 후보 전체(Step3까지의 응답 — `routes`는 항상 빈 배열, "
            "Step4는 사용자가 후보 하나를 고른 뒤에만 별도로 실행됨):"
        )
        lines.append("")
        lines.append("```json")
        lines.append(result.model_dump_json(indent=2))
        lines.append("```")
        lines.append("")

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"결과를 {_OUTPUT_PATH}에 썼습니다.")


if __name__ == "__main__":
    asyncio.run(main())

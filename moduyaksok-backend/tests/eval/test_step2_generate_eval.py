# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step2(generate_candidates) 성능평가 — 실제 LLM 호출, mock 없음.
#              골든 데이터셋(golden_step2.py)으로 후보 생성 품질을 GEval로 채점.
#              기본 pytest 실행에서 빠짐 — 돌리려면: pytest -m eval tests/eval
# 작성일      : 2026-08-09
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-09, 테스트 함수를 async def -> 동기 def + asyncio.run()으로 변경.
#             async def로 두면 pytest-asyncio가 이미 실행 중인 이벤트루프
#             안에서 이 테스트를 돌리게 되고, 그 상태에서 GEval.measure()가
#             내부적으로 또 loop.run_until_complete()를 걸다가(nest_asyncio
#             재진입) "RuntimeError: Timeout should be used inside a task"로
#             깨지는 걸 실측으로 확인(Step1 eval 테스트는 원래 동기 함수라
#             이 문제가 없었음 — test_step1_normalize_eval.py 참고). 동기
#             함수 + asyncio.run()으로 매 테스트마다 새 이벤트루프를 만들고
#             완전히 닫으면 GEval이 재진입할 "이미 실행 중인 루프"가 없어져
#             해결됨.
# ------------------------------------------------------------------
import asyncio

import pytest
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.pipeline.generate_step2 import generate_candidates
from app.pipeline.schemas import CandidateDraft
from tests.eval.golden_step2 import GOLDEN_STEP2_CASES

pytestmark = pytest.mark.eval

_QUALITY_CRITERIA = (
    "actual_output은 place_candidates 목록과 조건이 주어졌을 때 생성된 최대 3개의 "
    "일정 후보(candidate)를 'title=... activities=[...] rationale=...' 형태로 "
    "나열한 것이다. 각 activity는 'name(category, start_time-end_time)' 형태이고, "
    "input의 time_range는 이 일정 전체가 진행되는 시작~종료 시각이다. "
    "disliked_tags/liked_tags 각 항목은 이름과 verifiable(true 또는 false인 불리언 "
    "값 자체, '객관적'/'주관적' 같은 다른 문자열이 아님) 두 값으로 input에 표시돼 "
    "있다. 평가 기준: "
    "(1) 어떤 activity의 name이 input의 place_candidates 목록에 있는 title들 "
    "중 어느 것과도 일치하지 않으면(목록에 없는 장소를 지어낸 것) 크게 감점 "
    "(환각). place_candidates가 비어있는 경우는 이 기준에서 제외. "
    "(2) input의 disliked_tags 중 verifiable=true인 태그가 place_candidates의 "
    "category나 title로 명확히 판단되는 장소(예: '해산물' 태그면 category에 "
    "'해산물'이 포함된 장소)가 어느 candidate의 activity로든 등장하면 크게 감점 "
    "— verifiable=true인 disliked는 반드시 배제돼야 하는 하드 제약이다. "
    "(3) input의 disliked_tags 또는 liked_tags 중 verifiable=false인 태그(예: "
    "'사람 많은 곳', '조용한 분위기')가 실제로 하나라도 있을 때만 적용되는 기준이다 "
    "— 그 태그를 이유로 rationale에서 '사람이 없습니다', '매우 조용합니다'처럼 "
    "확인 불가능한 사실을 단정적으로 서술하면 감점(verifiable=false는 검증 수단이 "
    "없는 주관적 신호이므로 '비교적 한산한 편' 같은 hedge된 표현을 써야 한다). "
    "input의 liked_tags/disliked_tags가 둘 다 비어있거나 전부 verifiable=true라면 "
    "이 기준은 적용하지 마라(감점 금지) — 예산·시간처럼 확인 가능한 사실을 "
    "단정적으로 말하는 건 이 기준 위반이 아니다. "
    "(4) budget_per_person이 명시돼 있는데 파인다이닝처럼 명백히 고가로 보이는 "
    "카테고리의 장소를 예산 고려 없이 활동으로 넣었으면 감점. "
    "(5) actual_output에 candidate가 하나도 없으면(빈 결과) 크게 감점. "
    "(6) 어떤 activity의 start_time이나 end_time이 input의 time_range(시작~종료) "
    "범위를 벗어나면 감점. 같은 candidate 안에서 activity들의 시간대가 서로 겹치면 "
    "(예: 하나가 끝나기 전에 다음 게 시작) 감점. "
    "(7) 이 기준을 적용하기 전에 input의 place_candidates 목록 항목을 직접 세어라. "
    "그 개수가 4개 미만이면 이 기준은 적용하지 마라(감점 금지, 겹치는 게 당연함). "
    "4개 이상이고 카테고리 종류도 여러 개인 경우에만: 세 candidate가 활동 구성이 "
    "사실상 동일하거나 rationale만 다르고 실질적으로 같은 장소 조합을 고르면 감점 "
    "— 각 candidate는 자기 rationale이 주장하는 관점(가성비/동선/취향)에 따라 "
    "실제로 다른 선택을 반영해야 한다."
)


def _format_tags(tags) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(f"{t.tag}(verifiable={t.verifiable})" for t in tags) + "]"


def _format_place_candidates(place_candidates: list[dict]) -> str:
    if not place_candidates:
        return "[]"
    return "[" + ", ".join(f"{p['title']}({p['category']})" for p in place_candidates) + "]"


def _format_input(case) -> str:
    c = case.conditions
    start, end = c.time_range
    return (
        f"region={c.region}, time_range={start.isoformat()}~{end.isoformat()}, "
        f"budget_per_person={c.budget_per_person}, "
        f"liked_tags={_format_tags(c.liked_tags)}, "
        f"disliked_tags={_format_tags(c.disliked_tags)}, "
        f"place_candidates={_format_place_candidates(case.place_candidates)}"
    )


def _format_output(drafts: list[CandidateDraft]) -> str:
    if not drafts:
        return "(no candidates generated)"
    parts = []
    for d in drafts:
        activities = ", ".join(
            f"{a.name}({a.category}, {a.start_time}-{a.end_time})" for a in d.activities
        )
        parts.append(f"title={d.title!r} activities=[{activities}] rationale={d.rationale!r}")
    return "\n".join(parts)


_SEP = "=" * 100


def _print_report(case, drafts: list[CandidateDraft], metric: GEval) -> None:
    """-s로 돌렸을 때 터미널에서 바로 읽히게 하는 출력 전용 포맷. GEval 채점에 쓰는
    _format_input/_format_output(judge가 보는 텍스트, 채점 기준 문구가 그 포맷을
    그대로 언급함)은 안 건드리고, case/drafts 원본 데이터로 따로 예쁘게 찍는다.
    """
    c = case.conditions
    print(f"\n{_SEP}")
    print(f"[{case.name}]  score={metric.score:.2f} (threshold {metric.threshold})  "
          f"{'PASS' if metric.score >= metric.threshold else 'FAIL'}")
    print(f"{_SEP}")
    print(f"notes: {case.notes}\n")

    start, end = c.time_range
    print("--- input ---")
    print(f"  region            : {c.region}")
    print(f"  time_range        : {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}")
    print(f"  budget_per_person : {c.budget_per_person}")
    print(f"  liked_tags        : {_format_tags(c.liked_tags)}")
    print(f"  disliked_tags     : {_format_tags(c.disliked_tags)}")
    print("  place_candidates  :")
    if not case.place_candidates:
        print("    (없음)")
    for p in case.place_candidates:
        print(f"    - {p.get('title', '')} | {p.get('category', '')}")

    print("\n--- output ---")
    if not drafts:
        print("  (no candidates generated)")
    for i, d in enumerate(drafts, 1):
        print(f"  [candidate {i}] {d.title}")
        for a in d.activities:
            print(
                f"      - {a.name} ({a.category}) {a.start_time}-{a.end_time} "
                f"{a.price_range_per_person[0]}~{a.price_range_per_person[1]}원"
            )
        print(f"      rationale: {d.rationale}")
        if i != len(drafts):
            print()

    print("\n--- judge ---")
    print(f"  reason: {metric.reason}")
    print(f"{_SEP}\n")


@pytest.mark.parametrize("case", GOLDEN_STEP2_CASES, ids=lambda c: c.name)
def test_generate_candidates_quality(case, eval_credential, eval_judge_model):
    provider, api_key = eval_credential

    drafts = asyncio.run(
        generate_candidates(provider, api_key, case.conditions, case.place_candidates)
    )

    actual_output = _format_output(drafts)
    test_case = LLMTestCase(
        input=_format_input(case),
        actual_output=actual_output,
        additional_metadata={"notes": case.notes},
    )

    metric = GEval(
        name="Step2 후보 생성 품질",
        criteria=_QUALITY_CRITERIA,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=eval_judge_model,
        threshold=0.7,
    )
    metric.measure(test_case)

    # 통과/실패 상관없이 항상 출력 — pytest -m eval ... -s로 실행해야 바로 보인다
    _print_report(case, drafts, metric)

    assert metric.score >= metric.threshold, (
        f"[{case.name}] score={metric.score:.2f} reason={metric.reason}\n"
        f"notes={case.notes}\nactual_output={actual_output}"
    )

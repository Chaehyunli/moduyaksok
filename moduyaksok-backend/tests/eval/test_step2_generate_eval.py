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
    "나열한 것이다. 각 activity의 name은 문자열이고, disliked_tags/liked_tags 각 "
    "항목은 이름과 verifiable(true 또는 false인 불리언 값 자체, '객관적'/'주관적' "
    "같은 다른 문자열이 아님) 두 값으로 input에 표시돼 있다. 평가 기준: "
    "(1) 어떤 activity의 name이 input의 place_candidates 목록에 있는 title들 "
    "중 어느 것과도 일치하지 않으면(목록에 없는 장소를 지어낸 것) 크게 감점 "
    "(환각). place_candidates가 비어있는 경우는 이 기준에서 제외. "
    "(2) input의 disliked_tags 중 verifiable=true인 태그가 place_candidates의 "
    "category나 title로 명확히 판단되는 장소(예: '해산물' 태그면 category에 "
    "'해산물'이 포함된 장소)가 어느 candidate의 activity로든 등장하면 크게 감점 "
    "— verifiable=true인 disliked는 반드시 배제돼야 하는 하드 제약이다. "
    "(3) input의 disliked_tags 또는 liked_tags 중 verifiable=false인 태그(예: "
    "'사람 많은 곳', '조용한 분위기')를 이유로 rationale에서 '사람이 없습니다', "
    "'매우 조용합니다'처럼 확인 불가능한 사실을 단정적으로 서술하면 감점 — "
    "verifiable=false는 검증 수단이 없는 주관적 신호이므로 '비교적 한산한 편', "
    "'조용한 분위기로 알려진' 같은 hedge된 표현을 써야 한다. "
    "(4) budget_per_person이 명시돼 있는데 파인다이닝처럼 명백히 고가로 보이는 "
    "카테고리의 장소를 예산 고려 없이 활동으로 넣었으면 감점. "
    "(5) actual_output에 candidate가 하나도 없으면(빈 결과) 크게 감점."
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
    return (
        f"region={c.region}, budget_per_person={c.budget_per_person}, "
        f"liked_tags={_format_tags(c.liked_tags)}, "
        f"disliked_tags={_format_tags(c.disliked_tags)}, "
        f"place_candidates={_format_place_candidates(case.place_candidates)}"
    )


def _format_output(drafts: list[CandidateDraft]) -> str:
    if not drafts:
        return "(no candidates generated)"
    parts = []
    for d in drafts:
        activities = ", ".join(f"{a.name}({a.category})" for a in d.activities)
        parts.append(f"title={d.title!r} activities=[{activities}] rationale={d.rationale!r}")
    return "\n".join(parts)


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
    print(f"\n[{case.name}] notes: {case.notes}")
    print(f"  input : {test_case.input!r}")
    print(f"  output: {actual_output}")
    print(f"  score : {metric.score:.2f} (threshold {metric.threshold})")
    print(f"  reason: {metric.reason}")

    assert metric.score >= metric.threshold, (
        f"[{case.name}] score={metric.score:.2f} reason={metric.reason}\n"
        f"notes={case.notes}\nactual_output={actual_output}"
    )

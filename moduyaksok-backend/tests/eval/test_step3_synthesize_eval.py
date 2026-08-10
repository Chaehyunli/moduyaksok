# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step3(synthesize_and_validate) 성능평가 — 실제 LLM 호출, mock 없음.
#              골든 데이터셋(golden_step3.py)으로 "규칙만으로 못 잡는 판단"(verifiable
#              태그의 의미적 위반, 유사 후보 차별화, 소프트 신호 hedge)의 품질을
#              GEval로 채점. 기본 pytest 실행에서 빠짐 — 돌리려면: pytest -m eval tests/eval
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 실행에서 all_candidates_violate_same_hard_constraint_becomes_infeasible
#             케이스가 0.40으로 실패 — 실제 동작(전부 dropped, InfeasibleResponse)은
#             맞았는데 judge가 "kept가 0개라 (3)(4) 기준을 평가할 게 없다"를
#             "미흡함"으로 잘못 감점(Step2 eval에서도 겪은 것과 같은 "criteria가
#             애매해서 judge가 헷갈리는" 패턴). criteria에 "kept=0이면 (3)(4)는
#             자동 통과, 감점 금지"를 명시적으로 못박아 재실측 1.00으로 해결 —
#             나머지 3케이스는 최초 실행부터 0.80~1.00으로 통과.
# ------------------------------------------------------------------
import pytest
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.pipeline.schemas import CandidateDraft, InfeasibleResponse, PreferenceTag, ScheduleResponse
from app.pipeline.synthesize_step3 import synthesize_and_validate
from tests.eval.conftest import measure_with_retry
from tests.eval.golden_step3 import GOLDEN_STEP3_CASES

pytestmark = pytest.mark.eval

_QUALITY_CRITERIA = (
    "actual_output은 synthesize_and_validate()가 input의 후보(candidates) 중 몇 개를 "
    "최종 채택(kept)했고 몇 개를 드롭(dropped)했는지, kept된 각 후보의 "
    "why_recommended·feasibility_warning이 무엇인지 "
    "'kept=[{title, why_recommended, feasibility_warning}, ...] dropped=[title, ...]' "
    "형태로 보여준다. input의 disliked_tags/liked_tags 각 항목은 이름과 "
    "verifiable(true 또는 false인 불리언 값 그 자체, 다른 문자열이 아님) 두 값으로 "
    "표시돼 있다. input의 각 candidate는 'title=... activities=[name(category), ...]' "
    "형태로 나열돼 있다. 평가 기준: "
    "(1) input의 disliked_tags 중 verifiable=true인 태그가 어떤 candidate의 어떤 "
    "activity의 category나 name과 의미적으로 명확히 겹치면(예: '해산물' 태그, "
    "category에 '해산물' 포함) 그 candidate는 반드시 dropped에 있어야 한다 — kept에 "
    "남아있으면 크게 감점. "
    "(2) verifiable=false인 태그(liked/disliked 모두)를 이유로 후보가 dropped됐다고 "
    "보이면 감점 — 확인 불가능한 주관적 신호는 드롭 근거가 될 수 없다. "
    "(3) kept된 후보의 why_recommended나 feasibility_warning이 verifiable=false 태그와 "
    "관련해 확인 불가능한 사실을 단정적으로 서술하면(예: '사람이 없습니다', '매우 "
    "조용합니다') 감점 — 그 태그를 아예 언급 안 하는 건 감점 아니다, 언급할 거면 "
    "'비교적 한산한 편일 수 있어요'처럼 hedge된 표현이어야 한다. "
    "(4) kept된 candidate가 2개 이상이고 그중 활동 구성이 상당히 겹치는(활동 이름이 "
    "과반 이상 같은) 쌍이 있다면, 그 두 candidate의 why_recommended가 사실상 동일한 "
    "내용이거나 서로 다른 점을 전혀 언급하지 않으면 감점 — 각자 다른 부분(활동 구성 "
    "차이 등)을 실제로 언급해서 차별점을 설명해야 한다. "
    "(5) kept가 0개(모든 후보가 dropped)인데 input의 모든 candidate가 "
    "disliked_tags(verifiable=true) 위반처럼 명확한 하드 위반을 갖고 있지 않다면 "
    "감점 — 근거 없이 전부 드롭하면 안 된다. 반대로 모든 candidate가 실제로 그런 "
    "위반을 갖고 있다면 kept=0(dropped 전부)이 맞는 결과다 — 이건 감점 사유가 "
    "아니라 정답이다, 만점 받을 자격이 있는 정상 케이스로 취급해라. "
    "(6) why_recommended가 '이 후보가 다른 후보보다 낫다/1등이다'처럼 순위를 매기는 "
    "표현을 쓰면 감점 — 각 후보는 동등한 선택지이고 각자의 강점만 설명해야 한다. "
    "**중요**: kept가 0개인 경우 (3)번과 (4)번 기준은 애초에 평가할 kept 후보가 "
    "없으므로 자동으로 통과로 간주해라 — '평가할 대상이 없다'는 이유로 (3)(4)를 "
    "미흡·불완전하다고 감점하면 안 된다. kept=0일 때 실제로 확인해야 할 건 (1)(2)(5) "
    "뿐이고, 그것들만 맞으면 만점을 줘라."
)


def _format_tags(tags: list[PreferenceTag]) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(f"{t.tag}(verifiable={t.verifiable})" for t in tags) + "]"


def _format_candidates(candidates: list[CandidateDraft]) -> str:
    parts = []
    for c in candidates:
        activities = ", ".join(f"{a.name}({a.category})" for a in c.activities)
        parts.append(f"title={c.title!r} activities=[{activities}]")
    return "\n".join(parts)


def _format_input(case) -> str:
    c = case.conditions
    return (
        f"liked_tags={_format_tags(c.liked_tags)}, "
        f"disliked_tags={_format_tags(c.disliked_tags)}\n"
        f"candidates:\n{_format_candidates(case.candidates)}"
    )


def _format_output(input_candidates: list[CandidateDraft], result) -> str:
    if isinstance(result, InfeasibleResponse):
        dropped = [c.title for c in input_candidates]
        return f"kept=[] dropped={dropped} (InfeasibleResponse: {result.reason})"

    kept_titles = {c.title for c in result.candidates}
    dropped = [c.title for c in input_candidates if c.title not in kept_titles]
    kept_parts = [
        f"{{title={c.title!r}, why_recommended={c.why_recommended!r}, "
        f"feasibility_warning={c.feasibility_warning!r}}}"
        for c in result.candidates
    ]
    return f"kept=[{', '.join(kept_parts)}] dropped={dropped}"


_SEP = "=" * 100


def _print_report(case, result, actual_output: str, metric: GEval) -> None:
    print(f"\n{_SEP}")
    print(
        f"[{case.name}]  score={metric.score:.2f} (threshold {metric.threshold})  "
        f"{'PASS' if metric.score >= metric.threshold else 'FAIL'}"
    )
    print(f"{_SEP}")
    print(f"notes: {case.notes}\n")
    print("--- input candidates ---")
    print(_format_candidates(case.candidates))
    print("\n--- output ---")
    print(actual_output)
    print("\n--- judge ---")
    print(f"  reason: {metric.reason}")
    print(f"{_SEP}\n")


@pytest.mark.parametrize("case", GOLDEN_STEP3_CASES, ids=lambda c: c.name)
def test_synthesize_and_validate_quality(case, eval_credential, eval_judge_model):
    provider, api_key = eval_credential

    result: ScheduleResponse | InfeasibleResponse = synthesize_and_validate(
        provider, api_key, f"eval-{case.name}", case.conditions, case.candidates
    )

    actual_output = _format_output(case.candidates, result)
    test_case = LLMTestCase(
        input=_format_input(case),
        actual_output=actual_output,
        additional_metadata={"notes": case.notes},
    )

    metric = GEval(
        name="Step3 검증·병합 품질",
        criteria=_QUALITY_CRITERIA,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=eval_judge_model,
        threshold=0.7,
    )
    measure_with_retry(metric, test_case)

    # 통과/실패 상관없이 항상 출력 — pytest -m eval ... -s로 실행해야 바로 보인다
    _print_report(case, result, actual_output, metric)

    assert metric.score >= metric.threshold, (
        f"[{case.name}] score={metric.score:.2f} reason={metric.reason}\n"
        f"notes={case.notes}\nactual_output={actual_output}"
    )

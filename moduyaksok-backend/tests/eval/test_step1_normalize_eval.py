# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step1(normalize_conditions) 성능평가 — 실제 LLM 호출, mock 없음.
#              골든 데이터셋(golden_step1.py)으로 태그 추출 품질을 GEval로 채점.
#              기본 pytest 실행에서 빠짐 — 돌리려면: pytest -m eval tests/eval
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import datetime

import pytest
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.pipeline.normalize_step1 import normalize_conditions
from app.pipeline.schemas import PreferenceTag
from tests.eval.golden_step1 import GOLDEN_STEP1_CASES

pytestmark = pytest.mark.eval

_TAG_FAITHFULNESS_CRITERIA = (
    "actual_output은 '좋아하는 것: ...' / '싫어하는 것: ...' 원문에서 추출한 태그 "
    "목록이다. 각 태그는 이름과 verifiable(true 또는 false인 불리언 값 그 자체, "
    "다른 문자열이 아님) 두 값으로 표시돼 있다. 평가 기준: "
    "(1) 원문에 명시적으로 언급되지 않은 항목이 태그에 있으면 크게 감점 (할루시네이션). "
    "(2) 원문에 명확히 언급된 주요 항목이 태그에서 빠졌으면 감점 (누락). "
    "(3) '빼고', '못 먹어요' 같은 부정 표현의 대상이 disliked가 아니라 liked에 "
    "잘못 들어갔으면 크게 감점. liked 항목이 근거 없이 disliked에도 중복 등장하면 "
    "마찬가지로 크게 감점. "
    "(4) 원문이 비어있거나 구체적 언급이 없는데 태그가 채워져 있으면 크게 감점. "
    "(5) 음식 종류·구체적 장소/브랜드명처럼 장소 카테고리 데이터로 나중에 확인 "
    "가능한 태그의 verifiable 값이 false면 감점. 분위기·혼잡도처럼 확인할 데이터가 "
    "없는 주관적 태그의 verifiable 값이 true면 감점."
)


def _format_tags(tags: list[PreferenceTag]) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(f"{t.tag}(verifiable={t.verifiable})" for t in tags) + "]"


def _build_raw_input(liked_text: str, disliked_text: str) -> dict:
    return {
        "purpose": "date",
        "headcount": 2,
        "time_range": [datetime(2026, 8, 15, 10, 0), datetime(2026, 8, 15, 21, 0)],
        "region": "서울 잠실",
        "liked_text": liked_text,
        "disliked_text": disliked_text,
        "budget_per_person": 50000,
    }


@pytest.mark.parametrize("case", GOLDEN_STEP1_CASES, ids=lambda c: c.name)
def test_normalize_conditions_tag_extraction_quality(case, eval_credential, eval_judge_model):
    provider, api_key = eval_credential
    raw_input = _build_raw_input(case.liked_text, case.disliked_text)

    result = normalize_conditions(provider, api_key, raw_input)

    actual_output = (
        f"liked_tags={_format_tags(result.liked_tags)}, "
        f"disliked_tags={_format_tags(result.disliked_tags)}"
    )
    liked = case.liked_text or "(없음)"
    disliked = case.disliked_text or "(없음)"
    test_case = LLMTestCase(
        input=f"좋아하는 것: {liked}\n싫어하는 것: {disliked}",
        actual_output=actual_output,
        additional_metadata={"notes": case.notes},
    )

    metric = GEval(
        name="Step1 태그 추출 정확도",
        criteria=_TAG_FAITHFULNESS_CRITERIA,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=eval_judge_model,
        threshold=0.7,
    )
    metric.measure(test_case)

    # 통과/실패 상관없이 항상 출력 — pytest -m eval ... -s로 실행해야 바로 보인다
    # (-s 없으면 pytest가 stdout을 캡처해서 실패한 테스트에서만 보여줌).
    print(f"\n[{case.name}] notes: {case.notes}")
    print(f"  input : {test_case.input!r}")
    print(f"  output: {actual_output}")
    print(f"  score : {metric.score:.2f} (threshold {metric.threshold})")
    print(f"  reason: {metric.reason}")

    assert metric.score >= metric.threshold, (
        f"[{case.name}] score={metric.score:.2f} reason={metric.reason}\n"
        f"notes={case.notes}\nactual_output={actual_output}"
    )

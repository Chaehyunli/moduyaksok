# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : DEEPEVAL_*_API_KEY가 채워진 provider들(solar/gpt/claude)을 대상으로
#              Step1~3 골든셋(tests/eval/golden_step*.py)을 실제로 돌려서 provider별
#              GEval 점수(성능)와 토큰×가격(비용)을 나란히 비교한다. 목표: BYOK
#              사용자가 셋 중 뭘 등록하든 "비슷한 성능 + 비슷한 가격"이 나오는지
#              확인.
#              tests/eval/의 pytest 코드는 하나도 안 건드린다 — 거기 있는
#              criteria/포맷 함수/judge 로직(conftest.py)을 그대로 import해서
#              재사용만 한다. resolve_eval_credential()(첫 번째로 유효한 키 하나만
#              고르는 함수, upstage→openai→anthropic 순)도 안 건드리고 그대로
#              "judge 고르는 용도"로만 재사용 — pytest -m eval을 평소처럼 돌리면
#              지금 설정대로 solar만 과금되는 건 그대로 유지된다. 이 스크립트는
#              그것과 별개로, "3사 비교가 필요할 때"만 수동으로 실행하는 용도.
# 작성일      : 2026-08-12
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# 실행: cd moduyaksok-backend && source .venv/bin/activate
#      && python scripts/compare_providers_eval.py
# 결과: scripts/provider_comparison_report.md 를 매번 덮어쓴다.
# 전제: .env의 DEEPEVAL_UPSTAGE_API_KEY / DEEPEVAL_OPENAI_API_KEY /
#      DEEPEVAL_ANTHROPIC_API_KEY 중 값이 있고 ping이 성공하는 provider만 비교
#      대상에 들어간다(지금은 upstage/anthropic만 있고 openai는 비어있어서 둘만
#      비교됨 — 나중에 DEEPEVAL_OPENAI_API_KEY를 채우면 이 스크립트를 그대로
#      다시 돌리기만 하면 gpt도 자동으로 포함된다, 코드 수정 불필요).
# 주의: mock 없이 실제 LLM을 호출해서 과금된다(tests/eval/과 동일). 골든셋
#      개수(Step1 9 + Step2 4×관점3 + Step3 4) × 비교 대상 provider 수만큼 호출이
#      나가고, 채점(judge)도 매 케이스마다 별도로 호출된다 — provider 2개 기준
#      대략 target 50콜 + judge 34콜.
# ------------------------------------------------------------------
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.config import settings
from app.pipeline import generate_step2, normalize_step1, synthesize_step3
from app.pipeline.generate_step2 import generate_candidates
from app.pipeline.models import ModelTier, get_model
from app.pipeline.normalize_step1 import normalize_conditions
from app.pipeline.synthesize_step3 import synthesize_and_validate
from app.services.llm_ping import ping_provider
from tests.eval.conftest import ProviderJudgeModel, measure_with_retry, resolve_eval_credential
from tests.eval.golden_step1 import GOLDEN_STEP1_CASES
from tests.eval.golden_step2 import GOLDEN_STEP2_CASES
from tests.eval.golden_step3 import GOLDEN_STEP3_CASES
from tests.eval.test_step1_normalize_eval import _TAG_FAITHFULNESS_CRITERIA
from tests.eval.test_step1_normalize_eval import _build_raw_input as _step1_raw_input
from tests.eval.test_step1_normalize_eval import _format_tags as _step1_format_tags
from tests.eval.test_step2_generate_eval import _QUALITY_CRITERIA as _STEP2_CRITERIA
from tests.eval.test_step2_generate_eval import _format_input as _step2_format_input
from tests.eval.test_step2_generate_eval import _format_output as _step2_format_output
from tests.eval.test_step3_synthesize_eval import _QUALITY_CRITERIA as _STEP3_CRITERIA
from tests.eval.test_step3_synthesize_eval import _format_input as _step3_format_input
from tests.eval.test_step3_synthesize_eval import _format_output as _step3_format_output

_OUTPUT_PATH = Path(__file__).resolve().parent / "provider_comparison_report.md"

# 비교 대상 provider 후보 — 값이 없으면 자동으로 건너뛴다(DEEPEVAL_OPENAI_API_KEY를
# 나중에 채우면 코드 수정 없이 gpt도 비교 대상에 들어감).
_CANDIDATE_PROVIDERS: list[tuple[str, str | None]] = [
    ("upstage", settings.deepeval_upstage_api_key),
    ("openai", settings.deepeval_openai_api_key),
    ("anthropic", settings.deepeval_anthropic_api_key),
]

# 2026-08-12 각 provider 공식 가격 페이지 실측(1M 토큰당 USD) — app/pipeline/models.py
# 상단 주석과 같은 출처를 그대로 복사해왔다. 프로덕션 코드(models.py)는 모델 ID만
# 관리하는 곳이라 가격표까지 얹지 않으려고 여기 스크립트 전용으로 따로 둔다. 가격이
# 바뀌면 models.py 주석과 여기 둘 다 갱신할 것.
_PRICES_PER_1M: dict[tuple[str, ModelTier], tuple[float, float]] = {
    ("upstage", ModelTier.LOW): (0.15, 0.6),
    ("upstage", ModelTier.MID): (0.15, 0.6),
    ("upstage", ModelTier.HIGH): (0.15, 0.6),
    ("openai", ModelTier.LOW): (0.25, 2.00),
    ("openai", ModelTier.MID): (2.50, 15.0),
    ("openai", ModelTier.HIGH): (5.0, 30.0),
    ("anthropic", ModelTier.LOW): (1.0, 5.0),
    ("anthropic", ModelTier.MID): (3.0, 15.0),
    ("anthropic", ModelTier.HIGH): (5.0, 25.0),
}

# 각 step 파일의 실제 TIER 상수를 그대로 가져다 쓴다 — 예전엔 여기 별도로
# {1: LOW, 2: MID, 3: HIGH}로 추측해서 박아뒀다가, 실제로는 각 파일의 TIER가
# 문서(models.py의 ModelTier docstring)와 어긋나 있어서(Step1=MID, Step2=HIGH로
# 방치돼 있었음) 비용을 잘못 계산한 걸 발견(2026-08-12) — 다시는 안 어긋나게
# 소스를 하나로 통일.
_STEP_TIER = {
    1: normalize_step1.TIER,
    2: generate_step2.TIER,
    3: synthesize_step3.TIER,
}


def _cost_usd(provider: str, tier: ModelTier, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _PRICES_PER_1M[(provider, tier)]
    return input_tokens / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out


class _UsageCapture(logging.Handler):
    """call_structured()가 찍는 토큰 사용량 로그(2026-08-12 추가)를 가로챈다.
    Step2는 관점 3개를 스레드로 병렬 호출하는데(generate_step2._call_all_perspectives_sync),
    logging.Handler.handle()이 락을 잡고 호출돼서 여러 스레드가 동시에 emit해도
    레코드가 안 섞인다.
    """

    def __init__(self):
        super().__init__()
        self.records: list[tuple] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.args)


_usage_capture = _UsageCapture()
_structured_logger = logging.getLogger("app.services.structured_llm")
_structured_logger.addHandler(_usage_capture)
_structured_logger.setLevel(logging.INFO)


def _capture_start() -> int:
    return len(_usage_capture.records)


def _capture_collect(start: int) -> tuple[int, int]:
    entries = _usage_capture.records[start:]
    return sum(e[2] for e in entries), sum(e[3] for e in entries)


_THRESHOLD = 0.7


@dataclass
class CaseResult:
    step: int
    provider: str
    case_name: str
    score: float
    threshold: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None


def _resolve_target_providers() -> list[tuple[str, str]]:
    targets = []
    for provider, api_key in _CANDIDATE_PROVIDERS:
        if not api_key:
            continue
        try:
            ping_provider(provider, api_key)
        except Exception as exc:
            print(f"[skip] {provider}: ping 실패 ({exc})")
            continue
        targets.append((provider, api_key))
    return targets


def _run_step1(provider: str, api_key: str, judge: ProviderJudgeModel) -> list[CaseResult]:
    results = []
    for case in GOLDEN_STEP1_CASES:
        raw_input = _step1_raw_input(case.liked_text, case.disliked_text)
        start = _capture_start()
        try:
            result = normalize_conditions(provider, api_key, raw_input)
            input_tokens, output_tokens = _capture_collect(start)

            actual_output = (
                f"liked_tags={_step1_format_tags(result.liked_tags)}, "
                f"disliked_tags={_step1_format_tags(result.disliked_tags)}"
            )
            liked = case.liked_text or "(없음)"
            disliked = case.disliked_text or "(없음)"
            test_case = LLMTestCase(
                input=f"좋아하는 것: {liked}\n싫어하는 것: {disliked}",
                actual_output=actual_output,
            )
            metric = GEval(
                name="Step1 태그 추출 정확도",
                criteria=_TAG_FAITHFULNESS_CRITERIA,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                model=judge,
                threshold=_THRESHOLD,
            )
            measure_with_retry(metric, test_case)
            score, threshold, error = metric.score, metric.threshold, None
            print(
                f"  [step1][{provider}][{case.name}] score={score:.2f} "
                f"tokens={input_tokens}/{output_tokens}"
            )
        except Exception as exc:  # noqa: BLE001 — 한 케이스 실패로 전체 비교가 죽지 않게
            input_tokens, output_tokens = _capture_collect(start)
            score, threshold, error = 0.0, _THRESHOLD, str(exc)
            print(f"  [step1][{provider}][{case.name}] ERROR: {exc}")

        results.append(
            CaseResult(
                step=1,
                provider=provider,
                case_name=case.name,
                score=score,
                threshold=threshold,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=_cost_usd(provider, _STEP_TIER[1], input_tokens, output_tokens),
                error=error,
            )
        )
    return results


def _run_step2(provider: str, api_key: str, judge: ProviderJudgeModel) -> list[CaseResult]:
    results = []
    for case in GOLDEN_STEP2_CASES:
        start = _capture_start()
        try:
            drafts = asyncio.run(
                generate_candidates(provider, api_key, case.conditions, case.place_candidates)
            )
            input_tokens, output_tokens = _capture_collect(start)

            actual_output = _step2_format_output(drafts)
            test_case = LLMTestCase(input=_step2_format_input(case), actual_output=actual_output)
            metric = GEval(
                name="Step2 후보 생성 품질",
                criteria=_STEP2_CRITERIA,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                model=judge,
                threshold=_THRESHOLD,
            )
            measure_with_retry(metric, test_case)
            score, threshold, error = metric.score, metric.threshold, None
            print(
                f"  [step2][{provider}][{case.name}] score={score:.2f} "
                f"tokens={input_tokens}/{output_tokens} (관점 3개 합산)"
            )
        except Exception as exc:  # noqa: BLE001
            input_tokens, output_tokens = _capture_collect(start)
            score, threshold, error = 0.0, _THRESHOLD, str(exc)
            print(f"  [step2][{provider}][{case.name}] ERROR: {exc}")

        results.append(
            CaseResult(
                step=2,
                provider=provider,
                case_name=case.name,
                score=score,
                threshold=threshold,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=_cost_usd(provider, _STEP_TIER[2], input_tokens, output_tokens),
                error=error,
            )
        )
    return results


def _run_step3(provider: str, api_key: str, judge: ProviderJudgeModel) -> list[CaseResult]:
    results = []
    for case in GOLDEN_STEP3_CASES:
        start = _capture_start()
        try:
            result = synthesize_and_validate(
                provider, api_key, f"cmp-{provider}-{case.name}", case.conditions, case.candidates
            )
            input_tokens, output_tokens = _capture_collect(start)

            actual_output = _step3_format_output(case.candidates, result)
            test_case = LLMTestCase(input=_step3_format_input(case), actual_output=actual_output)
            metric = GEval(
                name="Step3 검증·병합 품질",
                criteria=_STEP3_CRITERIA,
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                model=judge,
                threshold=_THRESHOLD,
            )
            measure_with_retry(metric, test_case)
            score, threshold, error = metric.score, metric.threshold, None
            print(
                f"  [step3][{provider}][{case.name}] score={score:.2f} "
                f"tokens={input_tokens}/{output_tokens}"
            )
        except Exception as exc:  # noqa: BLE001
            input_tokens, output_tokens = _capture_collect(start)
            score, threshold, error = 0.0, _THRESHOLD, str(exc)
            print(f"  [step3][{provider}][{case.name}] ERROR: {exc}")

        results.append(
            CaseResult(
                step=3,
                provider=provider,
                case_name=case.name,
                score=score,
                threshold=threshold,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=_cost_usd(provider, _STEP_TIER[3], input_tokens, output_tokens),
                error=error,
            )
        )
    return results


def _build_report(results: list[CaseResult], judge_provider: str) -> str:
    providers = sorted({r.provider for r in results})
    lines = [
        "# Provider 비교 리포트 (성능 vs 비용)",
        "",
        f"마지막 실행: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"judge: `{judge_provider}` (`{get_model(judge_provider, ModelTier.HIGH)}`) 고정 — "
        "비교 대상 provider가 몇 개든 채점 기준이 흔들리지 않게 하나로 고정했다 "
        "(tests/eval/conftest.resolve_eval_credential()가 고른 것 그대로 재사용).",
        "",
        "파이프라인 그대로 재현: Step1(LOW, 1회 호출) → Step2(MID, 관점 3개 병렬 호출, "
        '토큰은 3개 합산) → Step3(HIGH, 1회 호출). `orchestrate.py`가 하는 "관점별 '
        '최대 1회 재시도"는 여기 반영 안 됨 — 실제 운영 비용은 이보다 약간 더 나올 '
        "수 있다.",
        "",
    ]

    for provider in providers:
        lines.append(f"## {provider}")
        lines.append("")
        lines.append("| step | case | score | pass | input_tok | output_tok | cost(USD) |")
        lines.append("|---|---|---|---|---|---|---|")

        step_costs: dict[int, list[float]] = {1: [], 2: [], 3: []}
        step_scores: dict[int, list[float]] = {1: [], 2: [], 3: []}
        errors: list[tuple[int, str, str]] = []
        for r in [r for r in results if r.provider == provider]:
            passed = "ERROR" if r.error else ("PASS" if r.score >= r.threshold else "FAIL")
            lines.append(
                f"| {r.step} | {r.case_name} | {r.score:.2f} | {passed} | "
                f"{r.input_tokens} | {r.output_tokens} | ${r.cost_usd:.4f} |"
            )
            step_costs[r.step].append(r.cost_usd)
            step_scores[r.step].append(r.score)
            if r.error:
                errors.append((r.step, r.case_name, r.error))
        lines.append("")

        if errors:
            lines.append("**실패(구조화 출력 등 예외로 채점 자체가 안 된 케이스)**")
            lines.append("")
            for step, case_name, error in errors:
                lines.append(f"- step{step} `{case_name}`: {error}")
            lines.append("")

        lines.append("**스텝별 평균**")
        lines.append("")
        lines.append("| step | avg score | avg cost(USD) |")
        lines.append("|---|---|---|")
        est_schedule_cost = 0.0
        for s in (1, 2, 3):
            costs = step_costs[s]
            scores = step_scores[s]
            avg_cost = sum(costs) / len(costs) if costs else 0.0
            avg_score = sum(scores) / len(scores) if scores else 0.0
            est_schedule_cost += avg_cost
            lines.append(f"| {s} | {avg_score:.2f} | ${avg_cost:.4f} |")
        lines.append("")
        lines.append(
            f"**일정 하나 생성 예상 비용(Step1+2+3 평균 합, 재시도 미포함): "
            f"${est_schedule_cost:.4f}**"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    targets = _resolve_target_providers()
    if not targets:
        print("비교할 provider가 없습니다 — .env의 DEEPEVAL_*_API_KEY를 확인하세요.")
        return

    judge_provider, judge_api_key = resolve_eval_credential()
    judge = ProviderJudgeModel(judge_provider, judge_api_key)
    print(f"[judge] {judge_provider} ({get_model(judge_provider, ModelTier.HIGH)})")
    print(f"[targets] {[p for p, _ in targets]}")

    all_results: list[CaseResult] = []
    for provider, api_key in targets:
        print(f"\n=== provider: {provider} ===")
        all_results += _run_step1(provider, api_key, judge)
        all_results += _run_step2(provider, api_key, judge)
        all_results += _run_step3(provider, api_key, judge)

    report = _build_report(all_results, judge_provider)
    _OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"\n결과를 {_OUTPUT_PATH}에 썼습니다.")


if __name__ == "__main__":
    main()

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
# 2026-08-09, _format_input/_print_report가 실제 프롬프트(_build_user_prompt)에
#             있는 purpose/headcount를 안 보여주고 있던 표시 누락을 보완.
#             region: str -> regions: list[str] 변경도 같이 반영.
# 2026-08-09, 재실행에서 실패 2건 재현·분석: soft_signal_crowdedness_needs_hedge는
#             카테고리 뒤섞임(generate_step2.py에서 보정)과 예산 합산 미준수가
#             원인, no_hallucinated_places_small_candidate_list는 place_candidates가
#             적을 때 같은 장소를 반복 방문시켜 time_range를 채우려는 패턴이 원인
#             (judge가 이를 "시간 겹침"으로 오판한 것도 겹침 — criteria (6) 겹침
#             정의를 더 명시적으로 재작성). criteria (8) 동일 장소 반복 방문 감점,
#             (9) 예산 합산 초과 감점 추가. judge(Solar)의 JSON 파싱 실패로 채점
#             자체가 깨지는 문제는 conftest.py의 measure_with_retry()로 완화.
# 2026-08-09, Step4 설계에서 "활동 간 겹침은 엄격, time_range 경계 초과·예산
#             초과는 관대(제한된 관용 범위 안이면 통과)"로 정책이 정해짐에 따라
#             criteria도 맞춤 — (6)을 겹침(6a, 항상 감점)과 time_range 경계
#             초과(6b, 1시간 이내는 정상)로 분리, (9)를 budget_per_person의
#             120% 이내는 정상으로 완화. Step2가 실제로 예산/시간을 딱 맞추길
#             기대하지 않는다 — 그건 Step4가 관용 범위로 최종 판단할 몫.
# ------------------------------------------------------------------
import asyncio

import pytest
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from app.pipeline.generate_step2 import generate_candidates
from app.pipeline.schemas import CandidateDraft
from tests.eval.conftest import measure_with_retry
from tests.eval.golden_step2 import GOLDEN_STEP2_CASES

pytestmark = pytest.mark.eval

_QUALITY_CRITERIA = (
    "actual_output은 place_candidates 목록과 조건(purpose/headcount/regions 포함)이 "
    "주어졌을 때 생성된 최대 3개의 "
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
    "(6a) 같은 candidate 안에서 activity들의 시간대가 서로 겹치면 항상 크게 감점 "
    "— 이건 정도의 문제가 아니라 구조적으로 불가능한 일정이라 예외 없이 감점한다. "
    "시간대가 '겹친다'는 건 정확히 이런 뜻이다: activity들을 시작 시각 순으로 "
    "정렬했을 때, 어떤 activity의 end_time이 바로 다음 activity의 start_time보다 "
    "늦은(더 큰) 경우다. 하나가 끝나는 시각과 다음 게 시작하는 시각이 같거나(예: "
    "12:00 종료 후 12:00 시작), 앞이 먼저 끝나고 그 다음에 다음 게 시작하면(예: "
    "12:00 종료, 12:30 시작) 이건 겹치는 게 아니다 — 절대 감점하지 마라. 실제로 "
    "시간 구간이 부분적으로라도 포개질 때만 감점. "
    "(6b) 어떤 activity의 start_time이 input의 time_range 시작 시각보다 1시간 "
    "넘게 이르거나, end_time이 time_range 종료 시각보다 1시간 넘게 늦으면 감점 "
    "— 1시간 이내로 벗어나는 건 감점하지 마라(예: time_range 종료가 21:00인데 "
    "마지막 activity가 21:30에 끝나는 정도는 정상, 22:30에 끝나면 감점 대상). "
    "실제 이동시간은 이 단계에서 아직 확정 전이라 이 정도 여유는 정상 범위다. "
    "(7) 이 기준을 적용하기 전에 input의 place_candidates 목록 항목을 직접 세어라. "
    "그 개수가 4개 미만이면 이 기준은 적용하지 마라(감점 금지, 겹치는 게 당연함). "
    "4개 이상이고 카테고리 종류도 여러 개인 경우에만: 세 candidate가 활동 구성이 "
    "사실상 동일하거나 rationale만 다르고 실질적으로 같은 장소 조합을 고르면 감점 "
    "— 각 candidate는 자기 rationale이 주장하는 관점(가성비/동선/취향)에 따라 "
    "실제로 다른 선택을 반영해야 한다. "
    "(8) 같은 candidate 안에서 동일한 place(같은 name)가 두 번 이상 activity로 "
    "등장하면 감점 — 시간을 채우려고 같은 곳을 반복 방문시키면 안 된다. "
    "place_candidates가 적어서 활동 개수가 적은 것 자체는 정상이니 감점하지 마라. "
    "(9) actual_output에 있는 각 candidate마다: 그 candidate의 모든 activity의 "
    "price_range_per_person 하한(첫 번째 숫자)을 다 더해서 input의 "
    "budget_per_person과 비교해라. 식당 등의 1인당 가격 자체가 추정 범위라 약간의 "
    "초과는 정상이다 — 합이 budget_per_person의 120% 이내면 감점하지 마라(예: "
    "budget_per_person이 50000이면 60000까지는 정상). 합이 budget_per_person의 "
    "120%를 넘으면 그때만 감점 — 특히 rationale이 '예산을 초과할 수 있다'처럼 "
    "초과 가능성을 인정하면서 그대로 제시했는데 그 정도로 많이 넘으면 더 크게 감점."
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
        f"purpose={c.purpose}, headcount={c.headcount}, "
        f"regions={c.regions}, time_range={start.isoformat()}~{end.isoformat()}, "
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
    print(f"  purpose           : {c.purpose}")
    print(f"  headcount         : {c.headcount}")
    print(f"  regions           : {c.regions}")
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
    measure_with_retry(metric, test_case)

    # 통과/실패 상관없이 항상 출력 — pytest -m eval ... -s로 실행해야 바로 보인다
    _print_report(case, drafts, metric)

    assert metric.score >= metric.threshold, (
        f"[{case.name}] score={metric.score:.2f} reason={metric.reason}\n"
        f"notes={case.notes}\nactual_output={actual_output}"
    )

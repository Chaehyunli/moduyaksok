# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 2 — 후보 생성 Fan-out (MoA Proposer). 관점이 다른 프롬프트
#              N=3개를 병렬 호출해 서로 다른 CandidateDraft를 만든다.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, PreferenceTag.verifiable 처리 방침 명시 — "사람 많은 곳"처럼 확인할
#             데이터가 없는 주관적 태그를 어떻게 다룰지 설계
# 2026-08-09, 실제 구현. call_structured가 동기 함수라 스레드풀로 감싸서
#             병렬화. 개별 관점 timeout 180초(실측 전이라 널널하게),
#             return_exceptions=True로 부분 실패 허용. 프롬프트는 RTF만 쓰고
#             few-shot은 생략 — 생성 작업에 few-shot을 넣으면 3개 관점이 예시
#             스타일로 수렴해 "실질적 차별성 확보"라는 이 Step의 목표를 해칠 수
#             있다고 판단.
# 2026-08-09, asyncio.wait_for(내부적으로 asyncio.timeout() 사용)가 DeepEval
#             eval 테스트 안에서 "RuntimeError: Timeout should be used inside a
#             task"로 3개 호출이 통째로 실패하는 문제를 실측으로 확인 — 원인은
#             DeepEval의 GEval.measure()가 내부적으로 거는 nest_asyncio 패치가
#             전역 상태라, 같은 프로세스 안에서 그 패치가 걸린 *이후*에 생성되는
#             모든 새 이벤트루프/태스크의 asyncio.timeout() current-task 감지가
#             깨짐(스크립트 단독 실행·같은 세션의 첫 eval 테스트는 정상, 두 번째
#             테스트부터 재현). asyncio.wait_for/asyncio.timeout을 아예 안 쓰는
#             구조로 변경 — concurrent.futures.Future.result(timeout=...)로
#             스레드 안에서 타임아웃을 처리하고, async 경계는
#             loop.run_in_executor 한 번만 넘는다.
# 2026-08-09, tests/eval/golden_step2.py의 budget_conscious_selection 케이스가
#             GEval 0.50/0.7로 실패 — place_candidates에 가격 정보가 없어서
#             모델이 예산 대비 카테고리 위험도를 스스로 추론해야 하는데,
#             프롬프트가 budget_per_person을 "지켜라"고만 하고 판단 기준을
#             안 줘서 파인다이닝 카테고리를 예산 무시하고 넣는 걸 실측으로 확인.
#             "카테고리 이름이 명백히 고가면 제외해라"를 Task에 명시해서 재실측
#             — 골든 4케이스 재통과(0.70~0.90).
# 2026-08-09, 골든 데이터의 place_candidates가 3~4개뿐이라 관점 3개가 결국 같은
#             장소들을 돌려써서 초안이 서로 비슷해지는 문제 확인 — 데이터 늘리는
#             것과 별개로, PERSPECTIVES 자체가 "이 관점을 최우선으로 고려해라: "
#             + 한 줄 라벨뿐이라 관점별로 뭘 다르게 해야 하는지가 모호했던 것도
#             원인. PERSPECTIVES를 (라벨, 상세 지시문) 쌍으로 바꿔서 관점마다
#             구체적 판단 기준(실내/실외 구분, 동선은 address 근접도로 판단, 취향
#             태그 최대 반영 기준)을 따로 명시.
# 2026-08-09, NormalizedConditions.region: str -> regions: list[str] 변경(Task 1)에
#             맞춰 _build_user_prompt가 지역을 콤마로 이어 붙여 전부 프롬프트에
#             주입하도록 수정.
# 2026-08-09, eval 재실행에서 재현된 미해결 이슈 3건 중 2건 해결:
#             (1) Solar가 activity의 name/category를 다른 place_candidates 항목
#             것과 뒤섞어 반환하는 결함 — 프롬프트로 못 고치는 모델 신뢰성 문제라,
#             반환 직전 _correct_categories()로 place_candidates 기준 category를
#             결정론적으로 재보정(LLM이 만든 category는 아예 안 믿음).
#             (2) 활동 가격 합이 budget_per_person을 넘는데도 "초과될 수 있다"고만
#             적고 그대로 내는 사례 실측 — Task에 "하한 합 계산해서 넘으면 다시
#             구성해라" 명시.
#             (3) place_candidates가 적을 때 같은 장소를 반복 방문시켜 time_range를
#             억지로 채우는 사례도 실측 — "같은 장소는 최대 1번만, 활동 개수 줄여도
#             된다"고 명시.
# ------------------------------------------------------------------
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.pipeline.models import ModelTier, get_model
from app.pipeline.schemas import CandidateDraft, NormalizedConditions, PreferenceTag
from app.services.structured_llm import call_structured

# MID -> HIGH로 격상(2026-08-09). 예산 합산·중복 방문 금지 지시를 추가하자 MID
# (solar-pro)가 하드 제약(환각 방지/verifiable=true/예산 합/중복 금지) + 소프트
# 신호 + 관점 3개를 동시에 못 버티는 걸 실측 확인 — rationale엔 "활동을 줄여
# 재설계한다"고 써놓고 실제 activities에는 반영을 안 하는 등 텍스트와 구조화
# 출력이 어긋나는 패턴이 나옴. Step1이 스키마 복잡화 때 겪은 것과 같은 패턴
# (PreferenceTag 2필드로 복잡해지자 LOW가 못 버텨서 MID로 올려 즉시 해결됨,
# 2026-08-07) — 여기서도 같은 처방으로 HIGH까지 올려서 재검증.
TIER = ModelTier.HIGH

# 관점을 다르게 줘서 후보 간 실질적 차별성을 확보한다 (기술설계 §4 Step 2).
# (라벨, 상세 지시문) 쌍 — 라벨만 주면 관점별로 뭘 다르게 판단해야 하는지 모델이
# 알아서 해석하게 되고, 그러면 place_candidates가 적을 때 세 관점이 결국 비슷한
# 선택으로 수렴한다(실측 확인, 2026-08-09). 관점마다 구체적 판단 기준을 명시.
PERSPECTIVES: tuple[tuple[str, str], ...] = (
    (
        "실내 중심, 가성비 우선",
        "category로 실내 장소임을 판단할 수 있는 곳(카페, 음식점, 실내 체험/전시/"
        "보드게임카페 등)을 우선 선택하고, 공원·산책로·야외 피크닉존처럼 명백히 "
        "실외인 장소는 피해라. price_range_per_person의 하한이 낮은 장소를 우선 "
        "배치해 budget_per_person 대비 여유를 최대한 남겨라.",
    ),
    (
        "동선 최소화 우선",
        "place_candidates의 address/roadAddress를 비교해서 서로 가장 가까운(같은 "
        "동·인접 구역) 장소들로만 구성해라. 다른 동·지역에 있는 장소를 섞지 말고, "
        "필요하면 활동 개수를 줄여서라도 이동 거리를 줄여라.",
    ),
    (
        "사용자 취향 태그 최대 반영",
        "liked_tags 중 verifiable=true인 태그와 category/title이 일치하는 장소를 "
        "최대한 많이 포함해라(가능하면 하나도 빠짐없이). verifiable=false인 "
        "liked_tags도 장소 유형(관광명소/한적한 동네 가게 등)으로 미루어 최대한 "
        "반영하되 절대 보장한다고 말하지 마라.",
    ),
)

# 개별 관점 호출 타임아웃(초). 각 호출이 실제로 얼마나 걸릴지 아직 실측 전이라
# 널널하게 잡음 — 실측 후 필요하면 좁힐 것 (기술설계 §4 "파이프라인 오류/타임아웃
# 처리"의 "예: 20초"는 참고 예시일 뿐, 이 프로젝트는 3분으로 결정).
TIMEOUT_SECONDS = 180

_ROLE_TASK = """\
# Role
너는 주어진 조건과 장소 후보 목록 안에서 만남 일정 초안을 만드는 전문 플래너다.

# Task
- place_candidates 목록에 있는 장소만 사용해라. 목록에 없는 장소를 지어내지 마라.
- headcount(인원 수), time_range(시작~종료 시각), budget_per_person(1인 예산) 조건을 \
지켜라. place_candidates에는 가격 정보가 없으니 category/title 이름만으로 판단해라 \
— '파인다이닝', '오마카세'처럼 카테고리 이름 자체가 명백히 고가를 뜻하는 장소는 \
budget_per_person이 낮으면(예: 2만원 이하) activities에서 제외해라.
- 활동을 다 고른 뒤, 각 activity의 price_range_per_person 하한을 모두 더해봐라. \
그 합이 budget_per_person을 넘으면 활동을 빼거나 더 저렴한 후보로 바꿔서 합이 \
budget_per_person 이내가 되게 다시 구성해라 — "넘을 수도 있다"고 rationale에 \
적어두는 걸로 대신하지 마라.
- 같은 장소는 한 초안 안에서 최대 1번만 써라. place_candidates가 적어서 \
time_range를 다 못 채우더라도 괜찮다 — 활동 개수를 줄여라. 같은 곳을 여러 번 \
반복 방문시켜서 시간을 억지로 채우지 마라.
- disliked_tags 중 verifiable=true인 태그는 place_candidates의 category/title로 \
판단해 반드시 배제해라.
- liked_tags 중 verifiable=true인 태그는 place_candidates의 category/title로 판단해 \
최대한 반영해라.
- verifiable=false인 태그(liked/disliked 모두)는 확인할 방법이 없는 주관적 취향이다 \
— 참고만 하고 절대 보장한다고 말하지 마라. rationale에서도 "사람이 없습니다"처럼 \
단정하지 말고 "비교적 한산한 편인 곳으로 골랐어요"처럼 hedge된 표현을 써라.
- 이번 초안은 다음 관점을 최우선으로 고려해라: {label}. 구체적으로: {instruction}

# Format
title(일정 제목), activities(각 항목은 name/category/start_time/end_time(HH:MM)/\
price_range_per_person(1인당 최소~최대 가격)), rationale(이 초안을 왜 이렇게 \
짰는지, {label} 관점을 어떻게 반영했는지 설명)\
"""


def _format_tags(tags: list[PreferenceTag]) -> str:
    if not tags:
        return "(없음)"
    return ", ".join(f"{t.tag}(verifiable={t.verifiable})" for t in tags)


def _format_place_candidates(place_candidates: list[dict]) -> str:
    if not place_candidates:
        return "(없음 — 이 조건으로는 활동을 채울 장소가 없다는 뜻이니 최소한의 \
초안만 만들어라)"
    lines = [
        f"- {p.get('title', '')} | {p.get('category', '')} | "
        f"{p.get('roadAddress') or p.get('address', '')}"
        for p in place_candidates
    ]
    return "\n".join(lines)


def _build_system_prompt(perspective: tuple[str, str]) -> str:
    label, instruction = perspective
    return _ROLE_TASK.format(label=label, instruction=instruction)


def _build_user_prompt(conditions: NormalizedConditions, place_candidates: list[dict]) -> str:
    start, end = conditions.time_range
    return (
        f"목적: {conditions.purpose}\n"
        f"인원: {conditions.headcount}명\n"
        f"시간: {start.isoformat()} ~ {end.isoformat()}\n"
        f"지역(복수 가능, place_candidates는 이 지역들에서 조회된 것): "
        f"{', '.join(conditions.regions)}\n"
        f"1인 예산: {conditions.budget_per_person}원\n"
        f"좋아하는 것: {_format_tags(conditions.liked_tags)}\n"
        f"싫어하는 것: {_format_tags(conditions.disliked_tags)}\n\n"
        f"장소 후보 목록(place_candidates):\n{_format_place_candidates(place_candidates)}"
    )


def _call_all_perspectives_sync(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[CandidateDraft | BaseException]:
    """스레드 하나 안에서 관점 3개를 병렬 제출하고, 각각 개별 timeout으로
    result()를 기다린다. asyncio.wait_for/asyncio.timeout을 쓰지 않아 이걸
    호출하는 async 쪽이 어떤 이벤트루프/nest_asyncio 상태에 있든 영향받지 않는다.
    """
    with ThreadPoolExecutor(max_workers=len(PERSPECTIVES)) as executor:
        future_to_perspective = {
            executor.submit(
                call_structured,
                provider=provider,
                api_key=api_key,
                model=get_model(provider, TIER),
                system=_build_system_prompt(perspective),
                user=_build_user_prompt(conditions, place_candidates),
                schema=CandidateDraft,
            ): perspective
            for perspective in PERSPECTIVES
        }
        results: list[CandidateDraft | BaseException] = []
        for future in future_to_perspective:
            try:
                results.append(future.result(timeout=TIMEOUT_SECONDS))
            except Exception as exc:
                results.append(exc)
        return results


def _correct_categories(draft: CandidateDraft, place_candidates: list[dict]) -> CandidateDraft:
    """LLM이 돌려준 activity.category는 못 믿는다 — Solar가 서로 다른 두 활동의
    name/category를 뒤섞어 반환하는 결함이 실측으로 확인됨(2026-08-09, golden_step2.py
    soft_signal_crowdedness_needs_hedge 등에서 재현). name이 place_candidates의
    title과 정확히 일치하면 category를 그 place_candidates 항목 것으로 덮어쓴다 —
    place_candidates는 이미 확정된 신뢰 데이터라 LLM이 다시 만들 필요가 없다.
    일치하는 title이 없으면(환각 의심) 손대지 않는다 — 그건 GEval 채점의 몫이다.
    """
    category_by_title = {p.get("title", ""): p.get("category", "") for p in place_candidates}
    corrected_activities = [
        activity.model_copy(update={"category": category_by_title[activity.name]})
        if activity.name in category_by_title
        else activity
        for activity in draft.activities
    ]
    return draft.model_copy(update={"activities": corrected_activities})


async def generate_candidates(
    provider: str,
    api_key: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
) -> list[CandidateDraft]:
    """PERSPECTIVES 각각에 대해 스레드풀로 병렬 LLM 호출, CandidateDraft 최대 3개 반환.

    place_candidates: 네이버 지역검색으로 사전 조회한 "지역 내 카테고리별 장소 후보
    목록" — LLM이 이 목록 안에서만 장소를 선택하도록 프롬프트에 주입해 환각을 막는다
    (기술설계 §4 Step 2). 이 함수 밖(장래 POST /schedules 라우터)에서 조회해서
    넘겨야 한다 — Step2는 "조건+장소 후보 → LLM 호출"만 하는 순수 함수로 유지해
    유닛 테스트가 네트워크 mock 없이 call_structured만 mock하면 되게 한다.

    conditions.liked_tags/disliked_tags는 PreferenceTag(tag, verifiable) 리스트다.
    verifiable=true는 하드 제약(반드시 반영/배제), verifiable=false는 소프트 신호
    (참고만, rationale도 hedge된 표현)로 프롬프트에서 다르게 지시한다(2026-08-07 결정).

    관점 3개 중 일부가 timeout(180초)이나 예외로 실패하면 해당 관점만 스킵하고
    나머지로 진행한다. 3개 다 실패하면 RuntimeError.

    반환 직전 각 활동의 category를 place_candidates 기준으로 재보정한다
    (_correct_categories) — LLM이 만든 category는 신뢰하지 않는다.
    """
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, _call_all_perspectives_sync, provider, api_key, conditions, place_candidates
    )
    drafts = [r for r in results if isinstance(r, CandidateDraft)]
    if not drafts:
        raise RuntimeError("Step2: 3개 관점 호출이 모두 실패했습니다.")
    return [_correct_categories(draft, place_candidates) for draft in drafts]

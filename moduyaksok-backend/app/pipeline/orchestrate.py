# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step1→2→3 순서로 실행해 경로 없는 후보(최대 3개)를 만든다.
#              Step3가 하드 위반으로 후보를 드롭하면, 그 후보를 만들었던 관점만
#              한 번 더 생성해서 다시 검증한다(관점별 최대 1회 재시도).
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. 원래 설계는 이 재시도를 synthesize_and_validate()(Step3)
#             안에서 하는 거였는데, 그러려면 Step3가 place_candidates와 "후보별
#             관점"까지 받아야 해서 Step2-Step3 결합이 커진다. 대신 이미 확립된
#             이 프로젝트 관례("각 Step은 다른 Step을 안 부르고, 여러 Step을
#             잇는 건 오케스트레이터/라우터 몫" — Step1/2/4 전부 이 패턴) 그대로
#             따라 별도 모듈로 뺐다. Step3 자체는 안 건드림(순수·이미 테스트된
#             상태 유지).
#
#             "몇 개 관점이 빠졌는지"는 Candidate/CandidateDraft 스키마에 필드를
#             추가하지 않고, title 문자열로 대조해서 알아낸다 — Step3가
#             draft.title을 그대로 Candidate.title로 복사하고(LLM이 새로 짓지
#             않음, synthesize_step3.py 참고) 관점마다 제목이 사실상 겹치지
#             않으니 이 매칭으로 충분하다.
#
#             재시도해도 InfeasibleResponse가 나올 수 있다(회복 불가능한 조건
#             — 예산이 애초에 너무 적은 경우 등) — 그러면 그대로 반환한다,
#             더 이상 재시도하지 않는다(관점별 최대 1회 원칙).
# 2026-08-11, place_candidates 조회(search_places_for_region)를 라우터에서 이
#             함수 안으로 옮김 — 태그 기반 검색(verifiable liked_tags/disliked_tags)
#             을 하려면 Step1이 만든 조건이 먼저 있어야 하는데, 지금까지는 라우터가
#             Step1 실행 전에 raw_input.region만으로 미리 검색해서 넘겨주는
#             구조였다(카테고리 검색만 하던 시절엔 문제없었음). "여러 Step을 잇는
#             건 오케스트레이터 몫"이라는 이 프로젝트 관례(이 파일 자체가 그 역할)
#             그대로, 장소 검색도 Step1 직후·Step2 직전이라는 정확한 위치에
#             놓이도록 이 함수 안으로 가져왔다. place_candidates 파라미터를 없애서
#             시그니처가 raw_input만 받게 바뀜 — 라우터/테스트 쪽도 맞춰 변경 필요.
# 2026-08-11(2차), regions: list[str] -> region: str로 축소되면서 search_places_
#             for_regions() -> search_places_for_region()으로 개명. 반환값도
#             result 단독에서 (result, conditions, place_candidates) 튜플로
#             변경 — 라우터가 SchedulePlacePool(신규 테이블, app/models/schedule.py)
#             을 같이 저장하려면 Step1 결과(conditions)와 장소 검색 결과
#             (place_candidates)가 필요한데, 지금까진 이 함수 밖으로 안 나갔다.
# ------------------------------------------------------------------
import asyncio
import logging
import time

from app.config import settings
from app.pipeline.generate_algorithm_step2 import (
    ensure_place_ids,
    generate_algorithm_candidates,
)
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
from app.services.naver_local_search import search_places_for_region

logger = logging.getLogger(__name__)


def _missing_perspectives(
    labeled_drafts: list[tuple[str, CandidateDraft]],
    result: ScheduleResponse | InfeasibleResponse,
) -> list[str]:
    if isinstance(result, InfeasibleResponse):
        # 전부 드롭돼서 InfeasibleResponse가 나온 경우, 시도했던 관점 전부가
        # "놓친 관점"이다.
        return [label for label, _ in labeled_drafts]
    survived_titles = {c.title for c in result.candidates}
    return [label for label, draft in labeled_drafts if draft.title not in survived_titles]


async def generate_schedule_candidates(
    provider: str,
    api_key: str,
    session_id: str,
    raw_input: dict,
) -> tuple[ScheduleResponse | InfeasibleResponse, NormalizedConditions, list[dict]]:
    """POST /schedules(장래)가 부를 진입점. Step1(조건 정규화) → 장소 검색(카테고리+
    태그) → Step2(후보 생성, 관점 라벨 유지) → Step3(검증·병합) 순서로 실행하고,
    Step3가 드롭한 관점이 있으면 그 관점만 generate_single_candidate()로 다시
    생성해 Step3를 한 번 더 돌린다(관점별 최대 1회).

    장소 검색이 Step1 다음에 있는 이유: verifiable liked_tags/disliked_tags 태그
    검색을 하려면 Step1이 만든 조건(구조화된 태그)이 먼저 있어야 한다
    (2026-08-11, naver_local_search.search_places_for_region 참고) — 예전엔
    카테고리 검색만 해서 Step1 이전(라우터)에서도 가능했지만 지금은 아니다.

    NaverSearchError(장소 검색 실패)는 여기서 잡지 않고 그대로 올린다 — 호출부
    (라우터)가 502로 변환한다.

    conditions(Step1 결과)와 place_candidates(장소 검색 결과)도 같이 반환한다
    (2026-08-11(2차)) — 라우터가 ScheduleSession과 함께 SchedulePlacePool을
    저장하려면 이 두 값이 필요한데, 둘 다 이 함수 안에서만 만들어지고 밖으로
    나가는 통로가 result뿐이었다. InfeasibleResponse가 나온 경우에도 라우터는
    DB row를 안 만들므로 place_candidates를 그냥 버리면 된다.

    사용자에게는 이 재시도가 안 보인다 — POST /schedules 응답이 나가기 전에
    이 함수 안에서 다 끝난다. Step1/2/3의 LLM 호출(call_structured)은 전부
    동기 함수라 loop.run_in_executor로 감싸 이벤트루프를 안 막는다
    (generate_candidates_with_perspectives는 이미 스스로 감싸고 있어 그대로 await).
    """
    loop = asyncio.get_running_loop()

    total_started = time.perf_counter()
    stage_started = time.perf_counter()
    conditions = await loop.run_in_executor(
        None, normalize_conditions, provider, api_key, raw_input
    )
    logger.info(
        "schedule_stage session_id=%s stage=normalize elapsed_seconds=%.3f",
        session_id,
        time.perf_counter() - stage_started,
    )

    stage_started = time.perf_counter()
    place_candidates = ensure_place_ids(
        await search_places_for_region(
            conditions.region,
            conditions.liked_tags,
            conditions.disliked_tags,
            session_id=session_id,
        )
    )
    logger.info(
        "schedule_stage session_id=%s stage=place_search elapsed_seconds=%.3f count=%s",
        session_id,
        time.perf_counter() - stage_started,
        len(place_candidates),
    )

    stage_started = time.perf_counter()
    result = await regenerate_schedule_candidates(
        provider,
        api_key,
        session_id,
        conditions,
        place_candidates,
    )
    logger.info(
        "schedule_stage session_id=%s stage=generate_and_synthesize "
        "elapsed_seconds=%.3f total_seconds=%.3f",
        session_id,
        time.perf_counter() - stage_started,
        time.perf_counter() - total_started,
    )
    return result, conditions, place_candidates


async def regenerate_schedule_candidates(
    provider: str,
    api_key: str,
    session_id: str,
    conditions: NormalizedConditions,
    place_candidates: list[dict],
    required_place_ids: tuple[str, ...] = (),
    precovered_liked_tags: tuple[str, ...] = (),
) -> ScheduleResponse | InfeasibleResponse:
    """저장된 조건·후보 풀로 일정 후보를 다시 만든다.

    필수 장소 피드백은 Step1·네이버 검색을 다시 실행하지 않는다. 최초 생성 때
    저장한 ``NormalizedConditions``와 ``SchedulePlacePool.places``를 그대로 써야
    사용자가 처음 입력한 선호·비선호 조건이 흔들리지 않고, 이미 검색한 장소를
    재사용할 수 있다. ``required_place_ids``는 Step2와 Step3 양쪽에서 하드 제약으로
    전달돼 모든 결과에 실제 포함될 때만 반환된다.
    """
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    place_candidates = ensure_place_ids(place_candidates)
    if settings.schedule_generator_mode == "hybrid":
        labeled_drafts = await loop.run_in_executor(
            None,
            generate_algorithm_candidates,
            provider,
            api_key,
            conditions,
            place_candidates,
            required_place_ids,
            precovered_liked_tags,
        )
        if not labeled_drafts:
            return InfeasibleResponse(
                detail="조건을 만족하는 일정 후보를 만들 수 없어요.",
                reason="필수 장소·식사·좋아요·동선 조건을 동시에 만족하는 장소 조합이 부족합니다.",
                adjustable_conditions=["required_places", "time_range", "region"],
            )
        result = await loop.run_in_executor(
            None,
            synthesize_and_validate,
            provider,
            api_key,
            session_id,
            conditions,
            [draft for _, draft in labeled_drafts],
        )
        logger.info(
            "schedule_regeneration session_id=%s draft_count=%s elapsed_seconds=%.3f",
            session_id,
            len(labeled_drafts),
            time.perf_counter() - started,
        )
        return result

    labeled_drafts = await (
        generate_candidates_with_perspectives(
            provider,
            api_key,
            conditions,
            place_candidates,
            required_place_ids,
            precovered_liked_tags,
        )
        if required_place_ids
        else generate_candidates_with_perspectives(provider, api_key, conditions, place_candidates)
    )
    if not labeled_drafts:
        return InfeasibleResponse(
            detail="필수 장소를 포함한 일정 후보를 만들 수 없어요.",
            reason="선택한 장소 주변에서 기존 시간·식사·동선 조건을 함께 만족하지 못했습니다.",
            adjustable_conditions=["required_places", "time_range", "region"],
        )

    result = await loop.run_in_executor(
        None,
        synthesize_and_validate,
        provider,
        api_key,
        session_id,
        conditions,
        [draft for _, draft in labeled_drafts],
    )

    missing = _missing_perspectives(labeled_drafts, result)
    if not missing:
        return result

    regenerated: list[CandidateDraft] = []
    for label in missing:
        try:
            args = (
                (
                    provider,
                    api_key,
                    conditions,
                    place_candidates,
                    label,
                    required_place_ids,
                    precovered_liked_tags,
                )
                if required_place_ids
                else (provider, api_key, conditions, place_candidates, label)
            )
            draft = await loop.run_in_executor(None, generate_single_candidate, *args)
            regenerated.append(draft)
        except Exception:
            continue  # 재시도도 실패하면 그 관점은 포기 — 최대 1회 원칙

    if not regenerated:
        return result

    surviving_drafts = [draft for label, draft in labeled_drafts if label not in missing]
    final_result = await loop.run_in_executor(
        None,
        synthesize_and_validate,
        provider,
        api_key,
        session_id,
        conditions,
        surviving_drafts + regenerated,
    )
    return final_result

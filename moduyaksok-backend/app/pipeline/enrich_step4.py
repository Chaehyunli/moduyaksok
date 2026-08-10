# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Step 4 — 이동 동선 보강. ODsay(lab.odsay.com) 호출, LLM 안 씀.
# 작성일      : 2026-08-07
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-07, 구간당 경로 1개 자동선택 → 여러 교통수단 옵션을 다 담아서
#             사용자가 프런트에서 직접 고르게 하는 방식으로 설계 변경
#             (RouteSegment.options). 조회 시각을 구간별 실제 출발 시각
#             기준으로 넣어야 한다는 점 명시.
# 2026-08-10, 실제 구현(당시 파일명 enrich_step3.py). 길찾기 프로바이더가 네이버
#             지도 -> ODsay로 확정되면서(docs/AI파이프라인_Step별_설계 Step4 절)
#             이 함수는 이제 파이프라인 전체가 아니라 "사용자가 3개 후보 중
#             하나를 고른 뒤" 그 후보 1개에만 호출된다(Step1→2→3→사용자 선택→4
#             순서로 재설계, 2026-08-10 논의) — 나머지 2개 후보의 ODsay 호출을
#             아예 안 하게 되어 ODsay Basic(일 1,000건)을 아낀다. 시간 파라미터
#             미지원이 실측 확인되어 "막차 확인" 기능은 포기 — operating_hours와
#             같은 패턴으로 프런트가 hedge된 안내만 보여준다. 차량(car) 모드는
#             프로바이더 미정으로 보류(카카오모빌리티 후보, 나중에 붙일 때 스키마
#             변경 불필요). 구간별 도보/대중교통 조회는 서로 독립적이라
#             asyncio.gather로 병렬 처리 — Step2가 좌표 기반으로 추정해둔 버퍼와
#             실제 값이 다르면 travel_estimate.reconcile_schedule()로 그 구간
#             이후 활동 시간을 당기거나 민다(추천 옵션 기준, 2026-08-10 결정:
#             초과분은 무조건 보정, 60분 넘는 여유만 당김).
# 2026-08-10, 파일명을 enrich_step3.py -> enrich_step4.py로 변경(코드 순서가
#             실행 순서와 어긋난다는 지적 — synthesize_and_validate가 검증만
#             하고 경로 데이터 없이도 동작하도록 먼저 실행되게 바뀌었으니, 그쪽을
#             Step3, 이 함수를 Step4로 라벨 스왑. 실행 순서 자체는 안 바뀜).
# 2026-08-10, get_transit_option()(대중교통 1개만) -> get_transit_options()(전부)로
#             바뀐 데 맞춰 이 함수도 조회된 모든 옵션을 RouteSegment.options에
#             그대로 담게 변경. RouteSegment.recommended_mode를
#             recommended_option_id/selected_option_id로 교체 — 초기 selected는
#             recommended와 같게 채우고, 시간 재조정(reconcile_schedule)도
#             recommended(=최초 selected) 기준 소요시간을 쓴다.
# ------------------------------------------------------------------
import asyncio
from datetime import datetime

from app.pipeline.schemas import (
    ActivityDraft,
    CandidateDraft,
    EnrichedCandidate,
    RouteOption,
    RouteSegment,
)
from app.pipeline.travel_estimate import reconcile_schedule
from app.services.odsay_directions import OdsayError, get_transit_options, get_walk_option

# 이 단계는 LLM을 쓰지 않는다(ODsay API 호출) — 모델 티어 해당 없음.


async def _fetch_segment_options(
    a: ActivityDraft, b: ActivityDraft
) -> tuple[list[RouteOption], str | None]:
    """구간 하나의 옵션을 조회한다. 좌표가 없으면(place_candidates에 없던 환각
    장소 등) 빈 옵션 + 경고 문자열을 돌려준다. ODsay 호출이 실패해도(네트워크 등)
    함수 전체가 죽지 않고 도보만 담아 진행한다 — 이 단계는 결정론적 API 호출이라
    한 구간의 실패가 나머지 구간까지 막을 이유가 없다.
    """
    if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
        return [], f"{a.name} → {b.name} 구간은 좌표를 찾지 못해 이동 정보를 채우지 못했습니다."

    walk = get_walk_option(a.lat, a.lng, b.lat, b.lng)
    try:
        transit_options = await get_transit_options(a.lat, a.lng, b.lat, b.lng)
    except OdsayError:
        return [walk], f"{a.name} → {b.name} 구간의 대중교통 정보를 가져오지 못했습니다."
    return [walk, *transit_options], None


async def enrich_routes(
    candidate: CandidateDraft, time_range: tuple[datetime, datetime]
) -> EnrichedCandidate:
    """활동 시퀀스 구간마다 도보(직선거리 추정)/대중교통(ODsay) 옵션을 조회해
    RouteSegment.options에 채운다. 대중교통은 ODsay가 한 응답에 준 경로를 전부
    담는다(지하철만/버스만/환승조합 등) — 하나만 골라서 나머지를 버리지 않는다.
    사용자가 원치 않는 교통편이 자동 확정되면 UX가 깨진다는 판단(2026-08-07 논의).
    `recommended_option_id`(최단 소요시간)는 프런트 기본 선택값이고,
    `selected_option_id`가 사용자가 실제로 확정한 값이다 — 초기값은
    recommended와 같게 채운다.

    Step2가 배정한 start_time/end_time은 좌표 기반 추정 버퍼를 쓴 값이라 실제와
    다를 수 있다 — 이 함수가 구간마다 recommended(=최초 selected) 옵션의 실제
    소요시간과 Step2 추정치를 비교해 reconcile_schedule()로 이후 활동들의 시간을
    보정한다. 이후 사용자가 selected_option_id를 다른 옵션으로 바꾸면 같은
    reconcile_schedule()을 그 시점에 다시 호출해 재조정하면 된다(프런트 연동 시).

    막차/첫차 여부는 확인하지 않는다 — ODsay searchPubTransPathT가 출발 시각
    파라미터를 지원하지 않아(실측 확인, 2026-08-10) 애초에 판단할 방법이 없다.
    operating_hours와 같은 패턴으로, 이르거나 늦은 시간대 이동은 사용자가 직접
    확인하도록 프런트가 hedge된 안내를 보여준다(이 함수의 책임 밖).
    """
    activities = list(candidate.activities)
    warnings: list[str] = []

    pairs = list(zip(activities, activities[1:], strict=False))
    fetched = await asyncio.gather(*(_fetch_segment_options(a, b) for a, b in pairs))

    routes: list[RouteSegment] = []
    for i, (options, warning) in enumerate(fetched):
        if warning:
            warnings.append(warning)
        if not options:
            continue

        recommended = min(options, key=lambda o: o.duration_minutes)
        # from_order/to_order는 1-based — 최종 Activity.order(Step3)가 1부터 매겨질
        # 순서 그대로 사용. selected_option_id 초기값은 recommended와 동일 —
        # 사용자가 나중에 바꾸면 그 시점에 이 필드만 갱신한다(프런트 연동 시).
        routes.append(
            RouteSegment(
                from_order=i + 1,
                to_order=i + 2,
                options=options,
                recommended_option_id=recommended.option_id,
                selected_option_id=recommended.option_id,
            )
        )

        estimated_buffer = int(
            (
                datetime.strptime(activities[i + 1].start_time, "%H:%M")
                - datetime.strptime(activities[i].end_time, "%H:%M")
            ).total_seconds()
            // 60
        )
        activities = reconcile_schedule(
            activities, i, estimated_buffer, recommended.duration_minutes
        )

    if activities:
        _, window_end = time_range
        last_end_time = datetime.strptime(activities[-1].end_time, "%H:%M").time()
        last_end = datetime.combine(window_end.date(), last_end_time)
        if last_end > window_end:
            warnings.append(
                f"실제 이동시간을 반영하면 마지막 활동이 {activities[-1].end_time}에 끝나 "
                f"희망 시간({window_end.strftime('%H:%M')})을 넘길 수 있습니다."
            )

    updated_draft = candidate.model_copy(update={"activities": activities})
    return EnrichedCandidate(
        draft=updated_draft,
        routes=routes,
        feasibility_warning=" ".join(warnings) if warnings else None,
    )

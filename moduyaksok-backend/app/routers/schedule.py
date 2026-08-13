# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /schedules, POST /schedules/{id}/routes,
#              POST /schedules/{id}/confirm, GET /schedules/{id}
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
# 2026-08-10, 최초 작성. 파이프라인 함수(orchestrate.generate_schedule_candidates,
#             enrich_step4.enrich_routes)는 이미 구현·테스트돼 있었고, 이 라우터가
#             그 함수들을 실제 HTTP 엔드포인트로 연결하는 얇은 접착 계층이다.
#             - DB row(ScheduleSession)는 파이프라인 성공 이후에만 만든다 —
#               실패 케이스(509/422)마다 만들었다 지우는 롤백 코드를 안 써도 됨.
#               session_id는 uuid4()로 미리 만들어 파이프라인에 넘기고, 성공하면
#               그 값을 그대로 PK로 써서 미리 만든 값과 실제 저장된 값이 어긋나지
#               않게 한다.
#             - candidates 컬럼(JSONB)은 항상 새 dict를 통째로 대입한다(부분
#               수정 X) — SQLAlchemy가 JSON 컬럼의 in-place mutation을 dirty로
#               못 잡는 문제(flag_modified 없이는 변경이 감지 안 됨)를 그냥
#               피하는 쪽으로 설계.
#             - InfeasibleResponse(409)는 HTTPException을 안 쓴다 — HTTPException의
#               detail은 항상 {"detail": ...}로 한 번 더 감싸이는데,
#               InfeasibleResponse 자체에 이미 detail/reason/adjustable_conditions
#               필드가 있어 감싸면 이중 중첩이 된다. JSONResponse로 바디를 그대로
#               반환해 API명세서 예시와 정확히 같은 모양을 만든다.
#             - Step4(enrich_routes)는 LLM을 안 써서 이 라우터의 /routes
#               엔드포인트는 BYOK 크리덴셜을 조회하지 않는다.
# 2026-08-10, 확정 시 공유 링크 생성. confirm_schedule()이 confirmed_candidate_id를
#             기록하고 ShareLink row를 만들어 8자 base62 slug를 ConfirmResponse에
#             실어 보낸다 — 다음 태스크(공개 조회 엔드포인트)가 이 slug로 세션을
#             찾는다.
# 2026-08-10, 전체 브랜치 리뷰 반영(Finding 1, 3). get_schedule()이 ShareLink를
#             조회해 ScheduleResponse.share_slug로 같이 돌려주게 함 — 새로고침 등
#             으로 confirm 응답을 놓쳐도 세션을 다시 조회해 slug를 복구할 수 있게.
#             ConfirmRequest에 selected_options(구간별 사용자가 고른 option_id)
#             추가 — confirm 시점에 후보의 저장된 routes에 반영(_replace_candidate
#             재사용)해서, 공유 화면이 recommended가 아니라 사용자가 실제로 고른
#             교통편을 보여주게 한다. _find_candidate 호출부를 존재만 검증하던
#             것에서 반환값을 쓰는 걸로 바꿈.
# 2026-08-11, search_places_for_region() 호출을 orchestrate.generate_schedule_candidates
#             안으로 옮기면서(태그 기반 검색이 Step1 조건을 필요로 해서,
#             orchestrate.py 참고) create_schedule()이 더 이상 직접 부르지 않게
#             변경 — NaverSearchError도 ValidationError와 같은 try 블록에서 잡음.
# 2026-08-11(2차), ScheduleCreateRequest.regions: list[str] -> region: str로 축소.
#             generate_schedule_candidates()가 (result, conditions, place_candidates)
#             튜플을 반환하게 바뀌어서, create_schedule()이 ScheduleSession과 같은
#             트랜잭션에서 SchedulePlacePool(신규 테이블)도 같이 저장한다 — 나중에
#             피드백 단계가 이미 검색한 장소·태그를 재사용할 수 있게 미리 쌓아둠.
# ------------------------------------------------------------------
import secrets
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from app.db import get_session
from app.models.llm_credential import LLMCredential
from app.models.schedule import (
    FeedbackMessage,
    SchedulePlacePool,
    ScheduleRequiredPlace,
    ScheduleSession,
    ShareLink,
)
from app.models.user import User
from app.pipeline.enrich_step4 import enrich_routes
from app.pipeline.orchestrate import generate_schedule_candidates, regenerate_schedule_candidates
from app.pipeline.schemas import (
    Candidate,
    InfeasibleResponse,
    NormalizedConditions,
    RequiredPlace,
    ScheduleResponse,
)
from app.services.auth import get_current_user
from app.services.credential import decrypt_key
from app.services.naver_local_search import NaverSearchError, place_id_for
from app.services.naver_map_url import build_naver_map_url

router = APIRouter()


class ScheduleCreateRequest(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    region: str
    liked_text: str = ""
    disliked_text: str = ""
    budget_per_person: int


class RoutesRequest(BaseModel):
    candidate_id: str


class SelectedOption(BaseModel):
    from_order: int
    option_id: str


class ConfirmRequest(BaseModel):
    candidate_id: str
    # 사용자가 후보 상세 화면에서 구간별로 고른 교통편. 비어있으면(예: 아직 경로를
    # 안 골랐거나 예전 클라이언트) 기존 recommended 선택을 그대로 둔다.
    selected_options: list[SelectedOption] = []


class ConfirmResponse(BaseModel):
    session_id: UUID
    status: str
    share_slug: str


class RequiredPlaceRequest(BaseModel):
    place_id: str


class ScheduleTitleRequest(BaseModel):
    title: str


class ConfirmedScheduleSummary(BaseModel):
    session_id: UUID
    title: str
    region: str
    candidate_title: str
    created_at: datetime


# ponytail: 8자 base62라 충돌 확률은 무시할 만한 수준(62^8 ≈ 218조) — 유니크
# 재시도 로직은 이 규모에서 과함. 실제로 충돌하면 DB unique 제약이 막고
# IntegrityError로 500이 나는데, 그 정도로 자주 일어날 확률이 아니다.
_SLUG_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _generate_slug(length: int = 8) -> str:
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(length))


def _get_user_credential(session: Session, user_id: UUID) -> LLMCredential:
    credential = session.exec(select(LLMCredential).where(LLMCredential.user_id == user_id)).first()
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 API 키가 없습니다.")
    return credential


def _get_owned_session(session: Session, session_id: UUID, user: User) -> ScheduleSession:
    schedule_session = session.get(ScheduleSession, session_id)
    if schedule_session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 일정입니다.")
    if schedule_session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "본인 소유의 일정만 조회할 수 있습니다.")
    return schedule_session


def _find_candidate(schedule_session: ScheduleSession, candidate_id: str) -> Candidate:
    for item in schedule_session.candidates.get("candidates", []):
        if item["candidate_id"] == candidate_id:
            return Candidate.model_validate(item)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 후보입니다.")


def candidate_with_source_categories(
    session: Session, schedule_session: ScheduleSession, candidate: Candidate
) -> Candidate:
    """구버전 저장 일정에도 후보 풀의 원래 15개 검색 카테고리를 복구한다."""
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == schedule_session.id)
    ).first()
    if place_pool is None:
        return candidate
    place_by_name = {
        str(place.get("title")): place
        for place in place_pool.places.get("places", [])
        if place.get("title")
    }
    required_place_ids = {
        place.place_id for place in _required_places_for_session(session, schedule_session.id)
    }
    enriched = candidate.model_copy(deep=True)
    for activity in enriched.activities:
        source = place_by_name.get(activity.name)
        if source:
            activity.source_category = activity.source_category or source.get("source_category")
            activity.place_id = activity.place_id or _place_with_id(source)["place_id"]
        activity.is_required = bool(activity.place_id and activity.place_id in required_place_ids)
    return enriched


def _replace_candidate(schedule_session: ScheduleSession, updated: Candidate) -> None:
    items = schedule_session.candidates.get("candidates", [])
    schedule_session.candidates = {
        "candidates": [
            updated.model_dump(mode="json")
            if item["candidate_id"] == updated.candidate_id
            else item
            for item in items
        ]
    }


def _empty_place_pool() -> dict:
    """구버전/테스트용 list 결과에도 일관된 API 모양을 제공한다."""
    return {"candidate_count": 0, "groups": {"liked": [], "disliked": [], "categories": []}}


def _place_pool_for_response(place_pool: dict) -> dict:
    """신규·레거시 검색 스냅샷 모두에 선택용 place_id를 제공한다."""
    groups = place_pool.get("groups", {})
    return {
        **place_pool,
        "groups": {
            kind: [
                {
                    **group,
                    "places": [
                        {
                            **place,
                            "place_id": place.get("place_id") or place_id_for(place),
                        }
                        for place in group.get("places", [])
                    ],
                }
                for group in groups.get(kind, [])
            ]
            for kind in ("liked", "disliked", "categories")
        },
    }


def _place_with_id(place: dict) -> dict:
    """저장 전/레거시 후보 풀에도 필수 장소용 안정 ID를 붙인다."""
    return {**place, "place_id": place.get("place_id") or place_id_for(place)}


def _find_place_in_pool(place_pool: SchedulePlacePool, place_id: str) -> dict | None:
    for raw_place in place_pool.places.get("places", []):
        place = _place_with_id(raw_place)
        if place["place_id"] == place_id:
            return place
    return None


def _required_place_from_raw(place: dict) -> RequiredPlace:
    return RequiredPlace(
        place_id=place["place_id"],
        name=place.get("title", ""),
        category=place.get("category", ""),
        address=place.get("roadAddress") or place.get("address", ""),
        map_url=build_naver_map_url(place),
    )


def _required_places_for_session(session: Session, session_id: UUID) -> list[RequiredPlace]:
    rows = session.exec(
        select(ScheduleRequiredPlace)
        .where(ScheduleRequiredPlace.session_id == session_id)
        .order_by(ScheduleRequiredPlace.created_at)
    ).all()
    return [
        RequiredPlace(
            place_id=row.place_id,
            name=row.name,
            category=row.category,
            address=row.address,
            map_url=row.map_url,
        )
        for row in rows
    ]


def _ensure_draft(schedule_session: ScheduleSession) -> None:
    # 확정된 일정도 목록에서 다시 열어 필수 장소·후보를 조정할 수 있다. 재확정하면
    # 기존 공유 링크는 유지되고, 링크가 가리키는 확정 후보만 최신 내용으로 바뀐다.
    return None


def _automatic_confirmed_titles(items: list[ScheduleSession]) -> dict[UUID, str]:
    """같은 지역의 확정 일정은 생성 순서로만 (1), (2)를 붙인다."""
    counts: dict[str, int] = {}
    titles: dict[UUID, str] = {}
    for item in sorted(items, key=lambda schedule: schedule.created_at):
        region = str(item.conditions.get("region", "지역 미정")).strip() or "지역 미정"
        occurrence = counts.get(region, 0)
        titles[item.id] = region if occurrence == 0 else f"{region} ({occurrence})"
        counts[region] = occurrence + 1
    return titles


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    body: ScheduleCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Step1(조건 정규화) → 장소 검색 → Step2(후보 생성) → Step3(검증·병합)까지
    실행해 경로 없는 후보(최대 3개)를 반환한다. 경로는 사용자가 후보를 고른 뒤
    POST /schedules/{session_id}/routes로 별도 조회한다(ODsay 호출 비용을 실제로
    볼 후보 1개로만 제한하기 위함 — docs/API명세서 참고).

    장소 검색(NaverSearchError 발생 지점)이 2026-08-11부터 generate_schedule_candidates
    안(Step1 직후)으로 옮겨져서, 여기서 별도로 먼저 호출하지 않는다 — 태그 기반
    검색을 하려면 Step1이 만든 조건이 먼저 있어야 하기 때문(orchestrate.py 참고).
    그래서 NaverSearchError도 ValidationError와 같은 try 블록에서 잡는다.
    """
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)

    session_id = uuid4()
    try:
        result, conditions, place_candidates = await generate_schedule_candidates(
            credential.provider, api_key, str(session_id), body.model_dump()
        )
    except NaverSearchError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"장소 검색에 실패했습니다: {exc}"
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if isinstance(result, InfeasibleResponse):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())

    place_pool = _place_pool_for_response(
        getattr(place_candidates, "search_groups", _empty_place_pool())
    )
    schedule_session = ScheduleSession(
        id=session_id,
        user_id=current_user.id,
        conditions=body.model_dump(mode="json"),
        normalized_conditions=conditions.model_dump(mode="json"),
        candidates={"candidates": [c.model_dump(mode="json") for c in result.candidates]},
    )
    session.add(schedule_session)
    # SchedulePlacePool.session_id는 FK라 schedule_session insert가 먼저 나가야
    # 한다 — 서로 relationship()으로 안 엮인 두 테이블이라 커밋 시점의 자동
    # 의존성 정렬을 믿지 말고 flush로 순서를 직접 보장한다.
    session.flush()
    session.add(
        SchedulePlacePool(
            session_id=session_id,
            places={"places": [_place_with_id(place) for place in place_candidates]},
            search_groups=place_pool,
            searched_liked_tags=[t.tag for t in conditions.liked_tags if t.verifiable],
            searched_disliked_tags=[t.tag for t in conditions.disliked_tags if t.verifiable],
        )
    )
    session.commit()

    return ScheduleResponse(
        session_id=str(session_id),
        candidates=result.candidates,
        place_pool=place_pool,
        required_places=[],
    )


@router.post("/schedules/{session_id}/routes", response_model=Candidate)
async def create_schedule_routes(
    session_id: UUID,
    body: RoutesRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """사용자가 3개 후보 중 하나를 고르면, 그 후보에 한해 Step4(enrich_routes)를
    실행해 구간별 이동 옵션을 채운 최종 1안을 반환한다.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidate = _find_candidate(schedule_session, body.candidate_id)

    start_raw, end_raw = schedule_session.conditions["time_range"]
    time_range = (datetime.fromisoformat(start_raw), datetime.fromisoformat(end_raw))

    enriched = await enrich_routes(candidate, time_range)

    _replace_candidate(schedule_session, enriched)
    session.add(schedule_session)
    session.commit()

    return enriched


@router.get("/schedules/{session_id}", response_model=ScheduleResponse)
def get_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """저장된 일정 세션 조회 (본인 소유만). POST .../routes를 아직 안 불렀으면
    해당 후보의 routes는 빈 배열이다. 확정 후 공유 링크가 만들어져 있으면
    share_slug도 같이 돌려준다 — 공유 화면이 새로고침돼도 슬러그를 다시 찾을 수 있게.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidates = [
        candidate_with_source_categories(session, schedule_session, Candidate.model_validate(item))
        for item in schedule_session.candidates.get("candidates", [])
    ]
    share_link = session.exec(
        select(ShareLink).where(ShareLink.session_id == schedule_session.id)
    ).first()
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == schedule_session.id)
    ).first()
    return ScheduleResponse(
        session_id=str(schedule_session.id),
        candidates=candidates,
        place_pool=_place_pool_for_response(place_pool.search_groups)
        if place_pool
        else _empty_place_pool(),
        required_places=_required_places_for_session(session, schedule_session.id),
        share_slug=share_link.slug if share_link else None,
    )


@router.get("/confirmed-schedules", response_model=list[ConfirmedScheduleSummary])
def list_confirmed_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내가 확정한 일정만, 목록에 필요한 가벼운 정보로 반환한다."""
    schedules = session.exec(
        select(ScheduleSession)
        .where(ScheduleSession.user_id == current_user.id, ScheduleSession.status == "confirmed")
        .order_by(ScheduleSession.created_at)
    ).all()
    automatic_titles = _automatic_confirmed_titles(schedules)
    result = []
    for schedule in reversed(schedules):
        candidate = (
            _find_candidate(schedule, schedule.confirmed_candidate_id)
            if schedule.confirmed_candidate_id
            else None
        )
        result.append(
            ConfirmedScheduleSummary(
                session_id=schedule.id,
                title=str(
                    schedule.conditions.get("display_title") or automatic_titles[schedule.id]
                ),
                region=str(schedule.conditions.get("region", "지역 미정")),
                candidate_title=candidate.title if candidate else "확정 일정",
                created_at=schedule.created_at,
            )
        )
    return result


@router.patch("/schedules/{session_id}/title", response_model=ConfirmedScheduleSummary)
def update_confirmed_schedule_title(
    session_id: UUID,
    body: ScheduleTitleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    schedule = _get_owned_session(session, session_id, current_user)
    if schedule.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 일정의 이름만 수정할 수 있습니다.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "일정 이름을 입력해주세요.")
    if len(title) > 80:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "일정 이름은 80자 이내로 입력해주세요."
        )
    # conditions는 이미 세션과 함께 JSONB로 영속된다. 새 컬럼을 요구하지 않아
    # 아직 마이그레이션하지 않은 배포 DB에서도 제목 수정이 바로 동작한다.
    schedule.conditions = {**schedule.conditions, "display_title": title}
    session.add(schedule)
    session.commit()
    candidate = (
        _find_candidate(schedule, schedule.confirmed_candidate_id)
        if schedule.confirmed_candidate_id
        else None
    )
    return ConfirmedScheduleSummary(
        session_id=schedule.id,
        title=title,
        region=str(schedule.conditions.get("region", "지역 미정")),
        candidate_title=candidate.title if candidate else "확정 일정",
        created_at=schedule.created_at,
    )


@router.delete("/schedules/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_confirmed_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """일정과 이 일정에 딸린 공유 링크·대화·생성 데이터까지 함께 제거한다."""
    schedule = _get_owned_session(session, session_id, current_user)
    if schedule.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 일정만 목록에서 삭제할 수 있습니다.")
    for model in (ShareLink, FeedbackMessage, ScheduleRequiredPlace, SchedulePlacePool):
        for row in session.exec(select(model).where(model.session_id == session_id)).all():
            session.delete(row)
    session.delete(schedule)
    session.commit()


@router.post("/schedules/{session_id}/required-places", response_model=RequiredPlace)
def add_required_place(
    session_id: UUID,
    body: RequiredPlaceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """후보 풀의 장소 하나를 이후 모든 재생성에 반드시 포함할 제약으로 저장한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 추가할 수 없습니다.")

    place = _find_place_in_pool(place_pool, body.place_id)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "검색한 후보 목록에 없는 장소입니다.")

    existing = session.exec(
        select(ScheduleRequiredPlace).where(
            ScheduleRequiredPlace.session_id == session_id,
            ScheduleRequiredPlace.place_id == body.place_id,
        )
    ).first()
    if existing is not None:
        return RequiredPlace(
            place_id=existing.place_id,
            name=existing.name,
            category=existing.category,
            address=existing.address,
            map_url=existing.map_url,
        )

    selected = _required_place_from_raw(place)
    session.add(
        ScheduleRequiredPlace(
            session_id=session_id,
            place_id=selected.place_id,
            name=selected.name,
            category=selected.category,
            address=selected.address,
            map_url=selected.map_url,
        )
    )
    session.commit()
    return selected


@router.delete(
    "/schedules/{session_id}/required-places/{place_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_required_place(
    session_id: UUID,
    place_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """필수 장소 제약만 해제한다. 표시 중인 기존 일정은 재생성 전까지 유지한다."""
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    row = session.exec(
        select(ScheduleRequiredPlace).where(
            ScheduleRequiredPlace.session_id == session_id,
            ScheduleRequiredPlace.place_id == place_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "필수 장소 목록에 없는 장소입니다.")
    session.delete(row)
    session.commit()


@router.post("/schedules/{session_id}/regenerate", response_model=ScheduleResponse)
async def regenerate_schedule(
    session_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """저장된 후보 풀에서 필수 장소를 모두 포함하는 새 일정 후보를 만든다.

    성공할 때만 기존 후보를 교체한다. 조건 충족이 불가능하면 409를 반환하되 기존
    후보는 보존하므로, 사용자는 필수 장소를 하나 해제한 뒤 다시 시도할 수 있다.
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    _ensure_draft(schedule_session)
    place_pool = session.exec(
        select(SchedulePlacePool).where(SchedulePlacePool.session_id == session_id)
    ).first()
    if place_pool is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "저장된 장소 후보가 없어 다시 생성할 수 없습니다."
        )

    required_places = _required_places_for_session(session, session_id)
    required_place_ids = tuple(place.place_id for place in required_places)
    place_candidates = [_place_with_id(place) for place in place_pool.places.get("places", [])]
    if not required_place_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "필수로 추가한 장소를 먼저 선택해주세요."
        )
    if any(_find_place_in_pool(place_pool, place_id) is None for place_id in required_place_ids):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "필수 장소가 저장된 후보 풀에서 사라졌습니다."
        )

    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)
    if schedule_session.normalized_conditions:
        conditions = NormalizedConditions.model_validate(schedule_session.normalized_conditions)
    else:
        # 이 필드는 추가 전 이미 만들어진 세션에는 없다. 그런 레거시 세션만 한 번
        # 정규화해 스냅샷을 채우고, 이후 반복 재생성은 항상 같은 값을 사용한다.
        from asyncio import get_running_loop

        from app.pipeline.normalize_step1 import normalize_conditions

        loop = get_running_loop()
        conditions = await loop.run_in_executor(
            None,
            normalize_conditions,
            credential.provider,
            api_key,
            schedule_session.conditions,
        )
        schedule_session.normalized_conditions = conditions.model_dump(mode="json")

    result = await regenerate_schedule_candidates(
        credential.provider,
        api_key,
        str(session_id),
        conditions,
        place_candidates,
        required_place_ids,
    )
    if isinstance(result, InfeasibleResponse):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())

    schedule_session.candidates = {
        "candidates": [candidate.model_dump(mode="json") for candidate in result.candidates]
    }
    # 확정된 일정에서 다시 생성했다면 새 후보를 확인한 뒤 다시 확정하게 한다.
    # 이때 기존 공유 링크는 지우지 않고, 재확정 시 같은 링크를 이어서 사용한다.
    if schedule_session.status == "confirmed":
        schedule_session.status = "draft"
        schedule_session.confirmed_candidate_id = None
    session.add(schedule_session)
    session.commit()
    return ScheduleResponse(
        session_id=str(session_id),
        candidates=result.candidates,
        place_pool=_place_pool_for_response(place_pool.search_groups),
        required_places=required_places,
    )


@router.post("/schedules/{session_id}/confirm", response_model=ConfirmResponse)
def confirm_schedule(
    session_id: UUID,
    body: ConfirmRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """후보 하나를 최종 확정(status: confirmed)하고 공유 링크를 만든다. draft ->
    confirmed는 한 방향만 허용 — 이미 confirmed인 세션은 재확정을 막는다
    (models/schedule.py 주석 참고). 사용자가 상세 화면에서 구간별로 고른 교통편
    (selected_options)이 있으면 확정 전에 후보의 저장된 routes에 반영한다 —
    공유 화면이 recommended가 아니라 사용자가 실제로 고른 걸 보여줘야 하므로
    (전체 브랜치 리뷰 Finding 3).
    """
    schedule_session = _get_owned_session(session, session_id, current_user)
    candidate = _find_candidate(schedule_session, body.candidate_id)

    if schedule_session.status == "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 확정된 일정입니다.")

    if body.selected_options:
        selections = {opt.from_order: opt.option_id for opt in body.selected_options}
        for route in candidate.routes:
            if route.from_order in selections:
                route.selected_option_id = selections[route.from_order]
        _replace_candidate(schedule_session, candidate)

    schedule_session.status = "confirmed"
    schedule_session.confirmed_candidate_id = body.candidate_id
    session.add(schedule_session)

    share_link = session.exec(
        select(ShareLink).where(ShareLink.session_id == schedule_session.id)
    ).first()
    if share_link is None:
        share_link = ShareLink(session_id=schedule_session.id, slug=_generate_slug())
        session.add(share_link)
    session.commit()

    return ConfirmResponse(
        session_id=schedule_session.id, status=schedule_session.status, share_slug=share_link.slug
    )

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
from app.models.schedule import ScheduleSession, ShareLink
from app.models.user import User
from app.pipeline.enrich_step4 import enrich_routes
from app.pipeline.orchestrate import generate_schedule_candidates
from app.pipeline.schemas import Candidate, InfeasibleResponse, ScheduleResponse
from app.services.auth import get_current_user
from app.services.credential import decrypt_key
from app.services.naver_local_search import NaverSearchError, search_places_for_regions

router = APIRouter()


class ScheduleCreateRequest(BaseModel):
    purpose: Literal["date", "friends", "family", "party", "other"]
    headcount: int
    time_range: tuple[datetime, datetime]
    regions: list[str]
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


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    body: ScheduleCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Step1(조건 정규화) → Step2(후보 생성) → Step3(검증·병합)까지 실행해
    경로 없는 후보(최대 3개)를 반환한다. 경로는 사용자가 후보를 고른 뒤
    POST /schedules/{session_id}/routes로 별도 조회한다(ODsay 호출 비용을 실제로
    볼 후보 1개로만 제한하기 위함 — docs/API명세서 참고).
    """
    credential = _get_user_credential(session, current_user.id)
    api_key = decrypt_key(credential.encrypted_key)

    try:
        place_candidates = await search_places_for_regions(body.regions)
    except NaverSearchError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"장소 검색에 실패했습니다: {exc}"
        ) from exc

    session_id = uuid4()
    try:
        result = await generate_schedule_candidates(
            credential.provider, api_key, str(session_id), body.model_dump(), place_candidates
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if isinstance(result, InfeasibleResponse):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=result.model_dump())

    schedule_session = ScheduleSession(
        id=session_id,
        user_id=current_user.id,
        conditions=body.model_dump(mode="json"),
        candidates={"candidates": [c.model_dump(mode="json") for c in result.candidates]},
    )
    session.add(schedule_session)
    session.commit()

    return ScheduleResponse(session_id=str(session_id), candidates=result.candidates)


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
        Candidate.model_validate(item) for item in schedule_session.candidates.get("candidates", [])
    ]
    share_link = session.exec(select(ShareLink).where(ShareLink.session_id == schedule_session.id)).first()
    return ScheduleResponse(
        session_id=str(schedule_session.id),
        candidates=candidates,
        share_slug=share_link.slug if share_link else None,
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

    share_link = ShareLink(session_id=schedule_session.id, slug=_generate_slug())
    session.add(share_link)
    session.commit()

    return ConfirmResponse(
        session_id=schedule_session.id, status=schedule_session.status, share_slug=share_link.slug
    )

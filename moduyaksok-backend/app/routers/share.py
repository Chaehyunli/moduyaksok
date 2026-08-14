# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : GET /share/{slug} — 확정된 일정을 인증 없이 공개 조회.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.schedule import ScheduleSession, ShareLink
from app.pipeline.schemas import Candidate
from app.routers.schedule import _find_candidate, candidate_with_source_categories

router = APIRouter()


class PublicShareLinkOut(BaseModel):
    slug: str


@router.get(
    "/public-share-links/{session_id}/candidates/{candidate_id}",
    response_model=PublicShareLinkOut,
)
def resolve_public_share_link(
    session_id: UUID,
    candidate_id: str,
    session: Session = Depends(get_session),
) -> PublicShareLinkOut:
    """기존 소유자용 공유 완료 URL을 공개 slug URL로 변환한다.

    확정된 후보와 URL의 candidate_id가 정확히 일치할 때만 slug를 반환한다.
    초안, 다른 후보, 존재하지 않는 세션은 모두 같은 404로 처리해 비공개 일정이나
    다른 후보의 존재 여부를 노출하지 않는다.
    """
    schedule_session = session.get(ScheduleSession, session_id)
    if (
        schedule_session is None
        or schedule_session.confirmed_candidate_id is None
        or schedule_session.confirmed_candidate_id != candidate_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")

    share_link = session.exec(
        select(ShareLink).where(ShareLink.session_id == schedule_session.id)
    ).first()
    if share_link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")
    return PublicShareLinkOut(slug=share_link.slug)


@router.get("/share/{slug}", response_model=Candidate)
def get_shared_schedule(slug: str, session: Session = Depends(get_session)):
    """slug로 확정된 후보 하나만 반환한다(다른 후보·조건·사용자 정보는 노출 안
    함) — 로그인 불필요. confirm 이전에는 ShareLink 자체가 없으므로 자동으로
    404가 된다.
    """
    share_link = session.exec(select(ShareLink).where(ShareLink.slug == slug)).first()
    if share_link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")

    schedule_session = session.get(ScheduleSession, share_link.session_id)
    if schedule_session is None or schedule_session.confirmed_candidate_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "존재하지 않는 링크입니다.")

    candidate = _find_candidate(schedule_session, schedule_session.confirmed_candidate_id)
    return candidate_with_source_categories(session, schedule_session, candidate)

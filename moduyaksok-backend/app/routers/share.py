# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : GET /share/{slug} — 확정된 일정을 인증 없이 공개 조회.
# 작성일      : 2026-08-10
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models.schedule import ScheduleSession, ShareLink
from app.pipeline.schemas import Candidate
from app.routers.schedule import _find_candidate

router = APIRouter()


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

    return _find_candidate(schedule_session, schedule_session.confirmed_candidate_id)

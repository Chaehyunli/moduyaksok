# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /auth/google, GET /me 엔드포인트
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models.user import User
from app.services.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SESSION_COOKIE_NAME,
    create_access_token,
    get_current_user,
    verify_google_id_token,
)

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str | None = None

    model_config = {"from_attributes": True}


def _session_cookie_options() -> dict:
    """로컬 HTTP와 운영(Vercel ↔ Render) HTTPS 모두에서 동작하는 쿠키 설정."""
    is_development = settings.env == "development"
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": not is_development,
        "samesite": "lax" if is_development else "none",
        "path": "/",
        "max_age": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/auth/google", response_model=UserOut)
def login_with_google(
    body: GoogleLoginRequest, response: Response, session: Session = Depends(get_session)
) -> UserOut:
    try:
        claims = verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = session.exec(select(User).where(User.google_id == claims["google_id"])).first()
    if user is None:
        user = User(google_id=claims["google_id"], email=claims["email"], name=claims["name"])
    else:
        user.email = claims["email"]
        user.name = claims["name"]
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user.id)
    response.set_cookie(value=token, **_session_cookie_options())
    return UserOut.model_validate(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    """브라우저 세션 쿠키를 즉시 제거한다."""
    options = _session_cookie_options()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=options["path"],
        httponly=options["httponly"],
        secure=options["secure"],
        samesite=options["samesite"],
    )
    return response


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)

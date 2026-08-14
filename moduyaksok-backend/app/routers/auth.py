# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /auth/google, GET /me 엔드포인트
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models.user import User
from app.services.auth import (
    SESSION_COOKIE_NAME,
    create_access_token,
    get_current_user,
    session_cookie_options,
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


def _upsert_google_user(session: Session, claims: dict) -> User:
    user = session.exec(select(User).where(User.google_id == claims["google_id"])).first()
    if user is None:
        user = User(google_id=claims["google_id"], email=claims["email"], name=claims["name"])
    else:
        user.email = claims["email"]
        user.name = claims["name"]
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _frontend_url() -> str:
    if settings.frontend_url:
        return settings.frontend_url.rstrip("/")
    return "http://localhost:5173" if settings.env == "development" else "https://moduyaksok.vercel.app"


@router.post("/auth/google", response_model=UserOut)
def login_with_google(
    body: GoogleLoginRequest, response: Response, session: Session = Depends(get_session)
) -> UserOut:
    try:
        claims = verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = _upsert_google_user(session, claims)
    token = create_access_token(user.id)
    response.set_cookie(value=token, **session_cookie_options())
    return UserOut.model_validate(user)


@router.post("/auth/google/redirect")
async def login_with_google_redirect(
    request: Request,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """iOS ITP 대응용 Google redirect 로그인 완료 지점.

    GIS가 application/x-www-form-urlencoded 본문으로 보낸 credential을 검증한다.
    g_csrf_token은 Google 권장 double-submit-cookie 방식으로 본문과 쿠키가 정확히
    일치해야 하며, 성공하면 기존 로그인과 같은 세션 쿠키를 발급한다.
    """
    form = parse_qs((await request.body()).decode("utf-8"))
    credential = form.get("credential", [""])[0]
    body_csrf = form.get("g_csrf_token", [""])[0]
    cookie_csrf = request.cookies.get("g_csrf_token", "")
    if not credential or not body_csrf or body_csrf != cookie_csrf:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google 로그인 요청을 확인할 수 없습니다.")

    try:
        claims = verify_google_id_token(credential)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = _upsert_google_user(session, claims)
    response = RedirectResponse(url=f"{_frontend_url()}/?google_login=success", status_code=303)
    response.set_cookie(value=create_access_token(user.id), **session_cookie_options())
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    """브라우저 세션 쿠키를 즉시 제거한다."""
    options = session_cookie_options()
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

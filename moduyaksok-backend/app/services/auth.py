# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : Google id_token 검증, 세션 JWT 발급/검증, 로그인 사용자 의존성
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.models.user import User

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
SESSION_REFRESH_THRESHOLD_MINUTES = 30

SESSION_COOKIE_NAME = "session"


def session_cookie_options() -> dict:
    """Return matching cookie options for login, refresh, and logout."""
    is_development = settings.env == "development"
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": not is_development,
        "samesite": "lax" if is_development else "none",
        "path": "/",
        "max_age": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def verify_google_id_token(id_token: str) -> dict:
    """Google id_token을 검증하고 (google_id, email, name)을 반환한다. 실패 시 ValueError."""
    try:
        payload = google_id_token.verify_oauth2_token(
            id_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        raise ValueError("유효하지 않은 Google id_token입니다.") from exc
    return {
        "google_id": payload["sub"],
        "email": payload["email"],
        "name": payload.get("name"),
    }


def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire}, settings.jwt_secret_key, algorithm=ALGORITHM
    )


def get_current_user(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "인증이 필요합니다.")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id = UUID(payload["sub"])
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "토큰이 유효하지 않습니다.") from exc
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "사용자를 찾을 수 없습니다.")
    # 활동 중인 사용자가 갑자기 로그아웃되지 않도록 만료 직전에 세션을 연장한다.
    # 이미 만료된 JWT는 위 jwt.decode에서 거부되므로 새 세션으로 되살아나지 않는다.
    refresh_after = timedelta(minutes=SESSION_REFRESH_THRESHOLD_MINUTES)
    if expires_at - datetime.now(UTC) <= refresh_after:
        response.set_cookie(value=create_access_token(user.id), **session_cookie_options())
    return user

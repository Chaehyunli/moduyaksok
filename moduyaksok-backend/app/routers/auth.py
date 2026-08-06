# ------------------------------------------------------------------
# 작성자      : 임채현
# 작성목적    : POST /auth/google, GET /me 엔드포인트
# 작성일      : 2026-08-06
# 변경사항 내역 (날짜, 변경목적, 변경내용 순으로 기입)
#
# ------------------------------------------------------------------
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.user import User
from app.services.auth import create_access_token, get_current_user, verify_google_id_token

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/auth/google", response_model=TokenResponse)
def login_with_google(
    body: GoogleLoginRequest, session: Session = Depends(get_session)
) -> TokenResponse:
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
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)

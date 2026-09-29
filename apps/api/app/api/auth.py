"""认证 API：登录 / 登出 / 当前用户 + 鉴权依赖。"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    is_session_valid,
    register_session,
    revoke_session,
)
from app.db import get_db
from models import User
from tools.security import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证凭据")
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"无效令牌: {exc}") from exc

    jti = payload.get("jti")
    if jti and not is_session_valid(jti):
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="用户已禁用")

    token, jti = create_access_token(user.id, user.username, user.role)
    register_session(jti, user.id, settings.jwt_expire_minutes * 60)
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserOut(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
        ),
    )


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    if credentials is not None:
        try:
            payload = decode_access_token(credentials.credentials)
            revoke_session(str(payload.get("jti")))
        except InvalidTokenError:
            pass
    return {"status": "ok", "message": "已登出"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )

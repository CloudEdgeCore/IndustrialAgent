"""认证安全：JWT 签发/校验 + Redis 会话注册（Redis 不可用时优雅降级）。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt as pyjwt
import redis as redis_client

from app.core.config import settings


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: int, username: str, role: str) -> tuple[str, str]:
    """返回 (token, jti)。"""
    jti = str(uuid4())
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, jti


def decode_access_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc


_redis: redis_client.Redis | None = None
_redis_checked = False


def _get_redis() -> redis_client.Redis | None:
    global _redis, _redis_checked
    if not _redis_checked:
        _redis_checked = True
        try:
            client = redis_client.Redis.from_url(
                settings.redis_url, socket_connect_timeout=2, socket_timeout=2
            )
            client.ping()
            _redis = client
        except Exception:  # noqa: BLE001 - Redis 不可用时降级为无状态 JWT
            _redis = None
    return _redis


def register_session(jti: str, user_id: int, ttl_seconds: int) -> None:
    client = _get_redis()
    if client is not None:
        try:
            client.setex(f"session:{jti}", ttl_seconds, str(user_id))
        except Exception:  # noqa: BLE001
            pass


def is_session_valid(jti: str) -> bool:
    client = _get_redis()
    if client is None:
        return True  # 降级：仅依赖 JWT 签名与有效期
    try:
        return bool(client.exists(f"session:{jti}"))
    except Exception:  # noqa: BLE001
        return True


def revoke_session(jti: str) -> None:
    client = _get_redis()
    if client is not None:
        try:
            client.delete(f"session:{jti}")
        except Exception:  # noqa: BLE001
            pass

"""认证安全单元测试：密码哈希 + JWT 签发/校验。"""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)
from tools.security import hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    stored = hash_password("admin123")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("admin123", stored)
    assert not verify_password("wrong-password", stored)


def test_password_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_verify_rejects_garbage() -> None:
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "md5$1$aa$bb")


def test_jwt_roundtrip() -> None:
    token, jti = create_access_token(7, "admin", "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["username"] == "admin"
    assert payload["role"] == "admin"
    assert payload["jti"] == jti


def test_jwt_expired_rejected() -> None:
    expired = pyjwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)


def test_jwt_tampered_rejected() -> None:
    token, _ = create_access_token(1, "user", "engineer")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "tampered")
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-token")

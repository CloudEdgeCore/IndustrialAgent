"""共享安全工具：密码哈希（PBKDF2-SHA256，纯标准库）。

data 层（演示账号种子）与 app 层（登录校验）共用。
"""

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )
    return f"{_PREFIX}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        prefix, iterations, salt, expected = stored.split("$")
        if prefix != _PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False

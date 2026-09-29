"""认证 API 集成测试：登录 / 会话 / 受保护端点（无库自动跳过）。"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import _get_redis
from app.main import app
from tools.db import normalize_database_url
from tools.settings import settings

pytestmark = pytest.mark.integration

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def require_seeded_db() -> None:
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM users WHERE username = 'admin'")
            if cur.fetchone()[0] == 0:
                pytest.skip("演示账号未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def _login_headers() -> dict:
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_success_and_me() -> None:
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    assert body["expires_in"] > 0

    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["display_name"] == "系统管理员"


def test_login_wrong_password() -> None:
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401

    missing = client.post(
        "/auth/login", json={"username": "nobody", "password": "x"}
    )
    assert missing.status_code == 401


def test_me_requires_token() -> None:
    assert client.get("/auth/me").status_code == 401
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer bad-token"}).status_code
        == 401
    )


def test_agent_endpoints_require_auth() -> None:
    assert client.post("/agent/chat", json={"query": "测试"}).status_code == 401
    assert client.get("/agent/sessions/any/messages").status_code == 401


def test_agent_chat_accepts_valid_token(scripted_llm) -> None:
    headers = _login_headers()
    app.state.agent_model = scripted_llm([])
    try:
        response = client.post("/agent/chat", json={"query": "测试"}, headers=headers)
        assert response.status_code == 200
    finally:
        del app.state.agent_model


def test_logout_revokes_session() -> None:
    if _get_redis() is None:
        pytest.skip("Redis 不可用，会话吊销降级为仅 JWT 校验")
    headers = _login_headers()
    assert client.get("/auth/me", headers=headers).status_code == 200

    logout = client.post("/auth/logout", headers=headers)
    assert logout.status_code == 200

    assert client.get("/auth/me", headers=headers).status_code == 401

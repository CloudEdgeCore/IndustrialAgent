"""SQL Tool 集成测试：真实数据库查询（无库自动跳过）+ 只读账号防线。"""

import os

import psycopg
import pytest

from tools.base import ToolContext
from tools.db import normalize_database_url, tool_db_connection
from tools.executor import execute_tool
from tools.settings import settings
from tools.sql import domain as _domain  # noqa: F401  触发注册
from tools.sql import tool as _tool  # noqa: F401  触发注册

pytestmark = pytest.mark.integration

EQUIPMENT_CTX = ToolContext(agent="equipment")
QUALITY_CTX = ToolContext(agent="quality")


@pytest.fixture(scope="module", autouse=True)
def require_seeded_db() -> None:
    url = normalize_database_url(
        os.environ.get("TOOL_DATABASE_URL", settings.tool_database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM equipment")
            if cur.fetchone()[0] == 0:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def test_query_equipment_count() -> None:
    result = execute_tool(
        "sql.query",
        {"dataset": "equipment", "select": ["equipment_id", "status"]},
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] == 30
    assert result.meta["source"] == "postgres:equipment"


def test_active_alarm_query() -> None:
    result = execute_tool(
        "sql.query",
        {
            "dataset": "alarms",
            "filters": [
                {"field": "equipment_id", "op": "=", "value": "EQ-003"},
                {"field": "alarm_code", "op": "=", "value": "E102"},
                {"field": "status", "op": "=", "value": "active"},
            ],
        },
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 1
    assert result.data[0]["alarm_code"] == "E102"


def test_quality_group_by_result() -> None:
    result = execute_tool(
        "sql.query",
        {
            "dataset": "quality_inspections",
            "filters": [{"field": "product_id", "op": "=", "value": "PRD-A"}],
            "group_by": ["result"],
        },
        QUALITY_CTX,
    )
    counts = {row["result"]: row["count"] for row in result.data}
    assert set(counts) == {"pass", "fail"}
    assert counts["pass"] > counts["fail"]


def test_time_range_query_hits_recent_alarms() -> None:
    result = execute_tool(
        "sql.query",
        {
            "dataset": "alarms",
            "filters": [{"field": "equipment_id", "op": "=", "value": "EQ-003"}],
            "time_range": {"relative": "last_24h"},
        },
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 1


def test_history_case_finds_coolant_record() -> None:
    result = execute_tool(
        "sql.history_case", {"equipment_id": "EQ-003"}, EQUIPMENT_CTX
    )
    assert result.meta["row_count"] >= 1
    assert any(row["root_cause"] == "冷却过滤器堵塞" for row in result.data)


def test_history_case_keyword_search() -> None:
    result = execute_tool(
        "sql.history_case", {"keyword": "冷却"}, EQUIPMENT_CTX
    )
    assert result.meta["row_count"] >= 1
    assert all(
        "冷却" in (row["description"] or "")
        + (row["root_cause"] or "")
        + (row["actions"] or "")
        for row in result.data
    )


def test_alarm_search_mode_with_enrichment() -> None:
    result = execute_tool(
        "sql.alarm_search",
        {"mode": "search", "equipment_id": "EQ-003"},
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 1
    assert all("alarm_name" in row for row in result.data)


def test_readonly_role_blocks_write() -> None:
    with tool_db_connection() as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("INSERT INTO defects (defect_code, name) VALUES ('zz', 'zz')")

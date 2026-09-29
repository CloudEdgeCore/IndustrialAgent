"""P2 Gate 安全测试：注入 / 越权 / 只读防线 全量攻击演练。

攻击面覆盖：
1. SQL 注入（值参数化、标识符白名单、数据集白名单、别名校验）
2. 权限越权（任意 Agent × 任意工具矩阵全覆盖）
3. 非法工具名 / 非 SELECT / 多语句 / 危险关键字（Validator 兜底）
4. 只读账号防线（数据库层纵深防御）
"""

import os

import psycopg
import pytest

from tools.base import (
    PermissionDeniedError,
    ToolContext,
    ToolNotFoundError,
    ToolValidationError,
)
from tools.db import normalize_database_url, tool_db_connection
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.permissions import AGENT_PERMISSIONS
from tools.registry import default_registry
from tools.settings import settings
from tools.sql.builder import build
from tools.sql.models import Filter, OrderBy, StructuredQuery
from tools.sql.planner import plan
from tools.sql.validator import validate_sql

load_all_tools()

ALL_TOOLS = [
    "sql.query",
    "sql.alarm_search",
    "sql.history_case",
    "timeseries.query",
    "analysis.run",
    "rag.search",
    "report.generate",
]

INJECTION_VALUES = [
    "'; DROP TABLE equipment; --",
    "1 OR 1=1",
    "'; DELETE FROM alarms WHERE '1'='1",
    "admin'--",
    "x' UNION SELECT * FROM users --",
]


def test_all_tools_registered() -> None:
    assert set(default_registry.names()) == set(ALL_TOOLS)


@pytest.mark.parametrize("evil", INJECTION_VALUES)
def test_sql_injection_values_stay_parameterized(evil: str) -> None:
    planned = plan(
        StructuredQuery(
            dataset="equipment",
            filters=[Filter(field="status", op="=", value=evil)],
        )
    )
    sql, params = build(planned)
    assert evil not in sql
    assert params["p0"] == evil
    validate_sql(sql, allowed_tables={"equipment"})


def test_sql_injection_like_value() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms",
            filters=[Filter(field="description", op="like", value="%'; DROP TABLE x; --")],
        )
    )
    sql, params = build(planned)
    assert "DROP" not in sql
    assert params["p0"].startswith("%")


def test_malicious_identifiers_rejected() -> None:
    with pytest.raises(ToolValidationError):
        plan(StructuredQuery(dataset="equipment; DROP TABLE x"))
    with pytest.raises(ToolValidationError):
        plan(StructuredQuery(dataset="equipment", select=["status; DROP TABLE x"]))
    with pytest.raises(ToolValidationError):
        plan(
            StructuredQuery(
                dataset="equipment", order_by=[OrderBy(field="1; DROP TABLE x")]
            )
        )
    with pytest.raises(ToolValidationError):
        plan(
            StructuredQuery(
                dataset="quality_inspections",
                metrics=[{"func": "count", "field": "*", "alias": "x; DROP TABLE y"}],
            )
        )


def test_timeseries_entity_injection_rejected() -> None:
    with pytest.raises(ToolValidationError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "EQ-003; DROP TABLE x", "metric": "temperature"},
            ToolContext(agent="equipment"),
        )


def test_validator_defense_in_depth() -> None:
    attacks = [
        "SELECT * FROM equipment; DROP TABLE equipment",
        "DELETE FROM equipment",
        "UPDATE equipment SET status = 'x'",
        "SELECT * FROM pg_shadow",
        "SELECT * FROM equipment WHERE pg_sleep(60) IS NULL",
        "SELECT * FROM information_schema.tables",
    ]
    for attack in attacks:
        with pytest.raises(ToolValidationError):
            validate_sql(attack, allowed_tables={"equipment"})


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ToolNotFoundError):
        execute_tool("sql.query; DROP TABLE x", {}, ToolContext(agent="equipment"))
    with pytest.raises(ToolNotFoundError):
        execute_tool("os.system", {}, ToolContext(agent="equipment"))


def test_permission_escalation_matrix() -> None:
    """每个 Agent 调用矩阵外工具必须被拒绝（全覆盖）。"""
    agents = ["router", "equipment", "process", "quality", "report", "unknown_agent"]
    checked = 0
    for agent in agents:
        allowed = AGENT_PERMISSIONS.get(agent, set())
        for tool in ALL_TOOLS:
            if tool in allowed:
                continue
            with pytest.raises(PermissionDeniedError):
                execute_tool(tool, {}, ToolContext(agent=agent))
            checked += 1
    assert checked >= 25


def test_permitted_calls_pass_permission_gate() -> None:
    """矩阵内工具不被权限层拦截（参数错误属于下一层）。"""
    with pytest.raises(ToolValidationError):
        execute_tool("sql.query", {"dataset": "nope"}, ToolContext(agent="equipment"))
    result = execute_tool(
        "analysis.run", {"op": "describe", "x": [1, 2, 3]}, ToolContext(agent="quality")
    )
    assert result.data["count"] == 3


@pytest.mark.integration
def test_readonly_database_defense() -> None:
    url = normalize_database_url(
        os.environ.get("TOOL_DATABASE_URL", settings.tool_database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")

    with conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone()[0] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            cur.execute("DELETE FROM equipment")
    conn.close()

    with tool_db_connection() as tool_conn:
        # 即使绕过只读标志（需在新事务生效），授权层（仅 SELECT）仍然拦截
        tool_conn.execute("SET default_transaction_read_only = off")
        tool_conn.commit()
        with tool_conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DROP TABLE equipment")


@pytest.mark.integration
def test_attack_via_executor_leaves_data_intact() -> None:
    url = normalize_database_url(
        os.environ.get("TOOL_DATABASE_URL", settings.tool_database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM equipment")
        if cur.fetchone()[0] == 0:
            conn.close()
            pytest.skip("数据未种子化")

    for evil in INJECTION_VALUES:
        result = execute_tool(
            "sql.query",
            {
                "dataset": "equipment",
                "filters": [{"field": "status", "op": "=", "value": evil}],
            },
            ToolContext(agent="equipment"),
        )
        assert result.meta["row_count"] == 0

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM equipment")
        assert cur.fetchone()[0] == 30, "攻击后数据必须完好无损"
    conn.close()

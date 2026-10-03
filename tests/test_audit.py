"""工具执行审计与 Validator 收口测试（无需数据库）。

安全要求（P7 加固）：
- **每一次调用尝试都要留痕**，包括权限拒绝与工具不存在；
- ``run_readonly_query`` 必须强制走 SQL Validator，且必须显式声明白名单表，
  不留下任何静默绕过路径。
"""

import json
import logging

import pytest

from tools.base import (
    PermissionDeniedError,
    ToolContext,
    ToolNotFoundError,
    ToolValidationError,
)
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.rag.search import _keyword_sql
from tools.sql.engine import run_readonly_query
from tools.sql.validator import validate_sql

load_all_tools()

AUDIT_LOGGER = "tools.audit"


def _audit_records(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == AUDIT_LOGGER
    ]


@pytest.fixture
def audit_capture(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
    return caplog


def test_permission_denied_is_audited(audit_capture) -> None:
    """越权尝试是最重要的安全信号，必须留痕。"""
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "EQ-003", "metric": "temperature"},
            ToolContext(agent="report"),
        )
    records = _audit_records(audit_capture)
    assert records, "权限拒绝必须写入审计日志"
    denied = [item for item in records if item["status"] == "denied"]
    assert denied and denied[0]["agent"] == "report"
    assert denied[0]["tool"] == "timeseries.query"
    assert "无权调用" in denied[0]["error"]


def test_unknown_tool_is_audited(audit_capture) -> None:
    with pytest.raises(ToolNotFoundError):
        execute_tool("tool.does_not_exist", {}, ToolContext(agent="equipment"))
    records = _audit_records(audit_capture)
    assert any(item["status"] == "not_found" for item in records)


def test_invalid_params_are_audited(audit_capture) -> None:
    from tools.base import ToolValidationError as _ToolValidationError

    with pytest.raises(_ToolValidationError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "DROP TABLE", "metric": "temperature"},
            ToolContext(agent="equipment"),
        )
    records = _audit_records(audit_capture)
    assert any(item["status"] == "invalid" for item in records)


def test_router_has_no_tool_permissions_and_is_audited(audit_capture) -> None:
    """Router 只负责调度，任何工具调用都应被拒绝并留痕。"""
    for tool_name, params in (
        ("sql.query", {"dataset": "equipment"}),
        ("rag.search", {"query": "E102"}),
    ):
        with pytest.raises(PermissionDeniedError):
            execute_tool(tool_name, params, ToolContext(agent="router"))
    assert len([item for item in _audit_records(audit_capture) if item["status"] == "denied"]) >= 2


def test_run_readonly_query_requires_explicit_allowlist() -> None:
    """allowed_tables 是必填关键字参数：不声明就无法执行。"""
    with pytest.raises(TypeError):
        run_readonly_query("SELECT 1", {})  # type: ignore[call-arg]


def test_run_readonly_query_validates_before_connecting() -> None:
    """校验先于建连：非白名单表在触库之前就被拒绝（无需数据库）。"""
    with pytest.raises(ToolValidationError):
        run_readonly_query(
            "SELECT 1 FROM pg_shadow", {}, allowed_tables={"equipment"}
        )
    with pytest.raises(ToolValidationError):
        run_readonly_query("SELECT 1; DROP TABLE equipment", {}, allowed_tables={"equipment"})


def test_rag_keyword_sql_passes_validator() -> None:
    """RAG 检索 SQL 也必须通过白名单校验（原先该路径完全绕过 Validator）。"""
    sql_text = _keyword_sql(["裂纹", "主轴"], [])
    validate_sql(sql_text, allowed_tables={"document_chunks", "documents"})


def test_rag_tables_are_declared_not_wildcard() -> None:
    from tools.rag.search import _RAG_TABLES

    assert _RAG_TABLES == {"document_chunks", "documents"}


def test_audit_logging_writes_visible_json_lines() -> None:
    """审计必须落到实际输出（此前无任何 handler，容器日志 0 条）。"""
    import io

    from tools.audit import (
        configure_audit_logging,
        record_tool_call,
        reset_audit_logging,
    )

    reset_audit_logging()
    stream = io.StringIO()
    try:
        configure_audit_logging(stream=stream)
        configure_audit_logging(stream=stream)  # 幂等：不得重复挂载 handler
        record_tool_call(
            agent="equipment",
            tool="sql.query",
            params={"dataset": "alarms", "limit": 5},
            status="ok",
            duration_ms=1.23,
            rows=5,
        )
    finally:
        reset_audit_logging()

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1, "重复初始化不应重复输出"
    payload = json.loads(lines[0])
    assert payload["event"] == "tool_call"
    assert payload["agent"] == "equipment"
    assert payload["status"] == "ok"
    assert payload["rows"] == 5
    assert payload["params"] == {"dataset": "alarms", "limit": 5}


def test_audit_summarize_handles_pydantic_and_long_values() -> None:
    from tools.audit import _summarize

    summarized = _summarize({"query": "x" * 300, "items": [1, 2, 3]})
    assert summarized["query"].endswith("...")
    assert len(summarized["query"]) == 203
    assert summarized["items"] == "<list[3]>"


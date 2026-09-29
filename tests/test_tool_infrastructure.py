"""Tool 层基础设施测试：注册表 / 权限矩阵 / 执行器 / 审计日志。"""

import logging

import pytest
from pydantic import BaseModel

from tools.base import (
    PermissionDeniedError,
    ToolContext,
    ToolExecutionError,
    ToolNotFoundError,
    ToolResult,
    ToolValidationError,
)
from tools.executor import execute_tool
from tools.permissions import check_permission
from tools.registry import ToolRegistry


class EchoParams(BaseModel):
    text: str
    count: int = 1


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register("sql.query", "回显工具", EchoParams)
    def echo(params: EchoParams, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            tool="sql.query",
            data={"text": params.text * params.count, "agent": ctx.agent},
            meta={"row_count": 1},
        )

    @reg.register("timeseries.query", "崩溃工具", EchoParams)
    def boom(params: EchoParams, ctx: ToolContext) -> ToolResult:
        raise RuntimeError("模拟数据库崩溃")

    return reg


def test_registry_lookup_and_not_found() -> None:
    reg = build_registry()
    assert reg.names() == ["sql.query", "timeseries.query"]
    spec = reg.get("sql.query")
    assert spec.description == "回显工具"
    with pytest.raises(ToolNotFoundError):
        reg.get("no.such.tool")


def test_registry_duplicate_register_raises() -> None:
    reg = build_registry()
    with pytest.raises(ValueError, match="重复注册"):
        reg.register("sql.query", "again", EchoParams)(lambda p, c: None)


def test_permission_matrix() -> None:
    check_permission("equipment", "sql.query")
    check_permission("quality", "analysis.run")

    with pytest.raises(PermissionDeniedError):
        check_permission("router", "sql.query")
    with pytest.raises(PermissionDeniedError):
        check_permission("equipment", "report.generate")
    with pytest.raises(PermissionDeniedError):
        check_permission("unknown_agent", "sql.query")


def test_execute_success() -> None:
    reg = build_registry()
    ctx = ToolContext(agent="equipment", session_id="s-1")
    result = execute_tool("sql.query", {"text": "ab", "count": 3}, ctx, registry=reg)
    assert result.data == {"text": "ababab", "agent": "equipment"}
    assert result.meta["row_count"] == 1


def test_execute_unknown_tool() -> None:
    reg = build_registry()
    with pytest.raises(ToolNotFoundError):
        execute_tool("nope", {}, ToolContext(agent="equipment"), registry=reg)


def test_execute_permission_denied_before_handler() -> None:
    reg = build_registry()
    with pytest.raises(PermissionDeniedError):
        execute_tool("sql.query", {"text": "x"}, ToolContext(agent="router"), registry=reg)


def test_execute_validation_error() -> None:
    reg = build_registry()
    with pytest.raises(ToolValidationError):
        execute_tool("sql.query", {"count": 2}, ToolContext(agent="equipment"), registry=reg)


def test_execute_wraps_unexpected_error() -> None:
    reg = build_registry()
    with pytest.raises(ToolExecutionError, match="模拟数据库崩溃"):
        execute_tool(
            "timeseries.query",
            {"text": "x"},
            ToolContext(agent="equipment"),
            registry=reg,
        )


def test_audit_log_records_calls(caplog: pytest.LogCaptureFixture) -> None:
    reg = build_registry()
    with caplog.at_level(logging.INFO, logger="tools.audit"):
        execute_tool("sql.query", {"text": "ok"}, ToolContext(agent="equipment"), registry=reg)
        with pytest.raises(ToolValidationError):
            execute_tool("sql.query", {}, ToolContext(agent="equipment"), registry=reg)

    messages = [r.getMessage() for r in caplog.records if r.name == "tools.audit"]
    assert len(messages) == 2
    assert '"status": "ok"' in messages[0]
    assert '"status": "invalid"' in messages[1]
    assert '"tool": "sql.query"' in messages[0]

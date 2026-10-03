"""统一工具执行入口：Registry → 权限校验 → 参数校验 → 执行 → 审计。

架构 §6 流程：Agent → Tool Registry → Permission Check → Tool Executor → Data Source

审计要求（P7 加固）：**每一次调用尝试都要留痕**，包括工具不存在与权限拒绝 ——
越权尝试恰恰是安全分析最需要的信号，原先在 try 之外被静默丢弃。
"""

from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from tools.audit import record_tool_call
from tools.base import (
    PermissionDeniedError,
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolResult,
    ToolValidationError,
)
from tools.permissions import check_permission
from tools.registry import ToolRegistry, default_registry


def _audit(
    context: ToolContext,
    *,
    tool: str,
    params: Any,
    status: str,
    duration_ms: float = 0.0,
    rows: int | None = None,
    error: str | None = None,
) -> None:
    record_tool_call(
        agent=context.agent,
        tool=tool,
        params=params,
        status=status,
        duration_ms=duration_ms,
        rows=rows,
        error=error,
        session_id=context.session_id,
        task_id=context.task_id,
    )


def execute_tool(
    name: str,
    params: dict[str, Any] | BaseModel | None,
    context: ToolContext,
    registry: ToolRegistry = default_registry,
) -> ToolResult:
    try:
        spec = registry.get(name)
    except ToolNotFoundError as exc:
        _audit(context, tool=name, params=params, status="not_found", error=str(exc))
        raise

    try:
        check_permission(context.agent, name)
    except PermissionDeniedError as exc:
        _audit(context, tool=name, params=params, status="denied", error=str(exc))
        raise

    if isinstance(params, BaseModel):
        raw: dict[str, Any] = params.model_dump()
    else:
        raw = dict(params or {})

    try:
        validated = spec.params_model(**raw)
    except ValidationError as exc:
        _audit(
            context,
            tool=name,
            params=raw,
            status="invalid",
            error=str(exc),
        )
        raise ToolValidationError(f"参数校验失败: {exc}") from exc

    started = perf_counter()
    try:
        result = spec.handler(validated, context)
    except ToolError as exc:
        _audit(
            context,
            tool=name,
            params=validated.model_dump(),
            status="error",
            duration_ms=(perf_counter() - started) * 1000,
            error=f"{exc.code}: {exc}",
        )
        raise
    except Exception as exc:  # noqa: BLE001 - 统一封装为工具执行错误
        _audit(
            context,
            tool=name,
            params=validated.model_dump(),
            status="error",
            duration_ms=(perf_counter() - started) * 1000,
            error=f"execution_error: {exc}",
        )
        raise ToolExecutionError(str(exc)) from exc

    rows = result.meta.get("row_count") if isinstance(result.meta, dict) else None
    _audit(
        context,
        tool=name,
        params=validated.model_dump(),
        status="ok",
        duration_ms=(perf_counter() - started) * 1000,
        rows=rows,
    )
    return result

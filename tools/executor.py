"""统一工具执行入口：Registry → 权限校验 → 参数校验 → 执行 → 审计。

架构 §6 流程：Agent → Tool Registry → Permission Check → Tool Executor → Data Source
"""

from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from tools.audit import record_tool_call
from tools.base import (
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolResult,
    ToolValidationError,
)
from tools.permissions import check_permission
from tools.registry import ToolRegistry, default_registry


def execute_tool(
    name: str,
    params: dict[str, Any] | BaseModel | None,
    context: ToolContext,
    registry: ToolRegistry = default_registry,
) -> ToolResult:
    spec = registry.get(name)
    check_permission(context.agent, name)

    if isinstance(params, BaseModel):
        raw: dict[str, Any] = params.model_dump()
    else:
        raw = dict(params or {})

    try:
        validated = spec.params_model(**raw)
    except ValidationError as exc:
        record_tool_call(
            agent=context.agent,
            tool=name,
            params=raw,
            status="invalid",
            duration_ms=0.0,
            error=str(exc),
            session_id=context.session_id,
            task_id=context.task_id,
        )
        raise ToolValidationError(f"参数校验失败: {exc}") from exc

    started = perf_counter()
    try:
        result = spec.handler(validated, context)
    except ToolError as exc:
        record_tool_call(
            agent=context.agent,
            tool=name,
            params=validated.model_dump(),
            status="error",
            duration_ms=(perf_counter() - started) * 1000,
            error=f"{exc.code}: {exc}",
            session_id=context.session_id,
            task_id=context.task_id,
        )
        raise
    except Exception as exc:  # noqa: BLE001 - 统一封装为工具执行错误
        record_tool_call(
            agent=context.agent,
            tool=name,
            params=validated.model_dump(),
            status="error",
            duration_ms=(perf_counter() - started) * 1000,
            error=f"execution_error: {exc}",
            session_id=context.session_id,
            task_id=context.task_id,
        )
        raise ToolExecutionError(str(exc)) from exc

    rows = result.meta.get("row_count") if isinstance(result.meta, dict) else None
    record_tool_call(
        agent=context.agent,
        tool=name,
        params=validated.model_dump(),
        status="ok",
        duration_ms=(perf_counter() - started) * 1000,
        rows=rows,
        session_id=context.session_id,
        task_id=context.task_id,
    )
    return result

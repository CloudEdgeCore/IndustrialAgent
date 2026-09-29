"""Tool 层基础类型：上下文、结果、错误体系。

架构红线（§4-2）：Agent 不直接访问数据库，一律经 Tool Layer。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolContext:
    """工具调用上下文（权限主体 = agent 名称）。"""

    agent: str
    session_id: str | None = None
    task_id: str | None = None


@dataclass
class ToolResult:
    """统一工具结果。meta 用于证据链与审计（来源 / 行数 / 耗时等）。"""

    tool: str
    data: Any
    meta: dict[str, Any] = field(default_factory=dict)


class ToolError(Exception):
    """工具执行错误基类。"""

    code = "tool_error"


class ToolNotFoundError(ToolError):
    code = "tool_not_found"


class PermissionDeniedError(ToolError):
    code = "permission_denied"


class ToolValidationError(ToolError):
    code = "validation_error"


class ToolExecutionError(ToolError):
    code = "execution_error"

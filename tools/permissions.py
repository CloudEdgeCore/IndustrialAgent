"""Agent → Tool 权限矩阵（最小权限原则）。

Agent 数量锁定：1 Router + 4 专业 Agent（架构红线 §4-1）。
未登记 Agent / 未授权工具一律拒绝。
"""

from tools.base import PermissionDeniedError

AGENT_PERMISSIONS: dict[str, set[str]] = {
    "router": set(),
    "equipment": {
        "sql.query",
        "sql.alarm_search",
        "sql.history_case",
        "timeseries.query",
        "rag.search",
        "analysis.run",
    },
    "process": {
        "sql.query",
        "timeseries.query",
        "rag.search",
        "analysis.run",
    },
    "quality": {
        "sql.query",
        "timeseries.query",
        "rag.search",
        "analysis.run",
    },
    "report": {
        "report.generate",
    },
}


def check_permission(agent: str, tool_name: str) -> None:
    allowed = AGENT_PERMISSIONS.get(agent, set())
    if tool_name not in allowed:
        raise PermissionDeniedError(
            f"agent '{agent}' 无权调用工具 '{tool_name}'"
        )

"""工具调用审计日志（JSON Lines → logging）。

架构 §6：Tool Layer 统一记录调用日志；P6 接入 Langfuse 后可扩展为全链路追踪。
"""

import json
import logging
from typing import Any

logger = logging.getLogger("tools.audit")


def record_tool_call(
    *,
    agent: str,
    tool: str,
    params: Any,
    status: str,
    duration_ms: float,
    rows: int | None = None,
    error: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
) -> None:
    payload = {
        "event": "tool_call",
        "agent": agent,
        "tool": tool,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "rows": rows,
        "error": error,
        "session_id": session_id,
        "task_id": task_id,
        "params": _summarize(params),
    }
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def _summarize(params: Any) -> Any:
    if params is None:
        return None
    if isinstance(params, dict):
        out = {}
        for key, value in params.items():
            if isinstance(value, list):
                out[key] = f"<list[{len(value)}]>"
            elif isinstance(value, str) and len(value) > 200:
                out[key] = value[:200] + "..."
            else:
                out[key] = value
        return out
    text = str(params)
    return text[:500]

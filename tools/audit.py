"""工具调用审计日志（JSON Lines）。

架构 §6：Tool Layer 统一记录调用日志；P6 接入 Langfuse 后可扩展为全链路追踪。

可见性要求（P7 加固）
--------------------
审计只有落到实际输出才有意义。此前只写入 ``tools.audit`` logger，而项目从未配置
任何 handler，导致容器日志里 **0 条** 审计记录 —— 声称的"审计日志"实际不可见。
现在由 ``configure_audit_logging()`` 显式挂载 stdout handler（Docker 直接采集），
并由 API 启动与工具 CLI 入口调用。
"""

import json
import logging
import sys
from typing import Any

logger = logging.getLogger("tools.audit")

_configured = False


def configure_audit_logging(level: int = logging.INFO, stream: Any = None) -> logging.Logger:
    """把审计日志接到实际输出（默认 stdout）。

    幂等；保留 ``propagate``，以便测试的 ``caplog`` 与应用日志配置仍能采集到记录。
    """
    global _configured
    if _configured:
        return logger
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    _configured = True
    return logger


def reset_audit_logging() -> None:
    """移除已挂载的 handler（测试 / 重复初始化时使用）。"""
    global _configured
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    _configured = False


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
    if hasattr(params, "model_dump"):  # pydantic 模型（权限拒绝路径可能直接传入）
        params = params.model_dump()
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

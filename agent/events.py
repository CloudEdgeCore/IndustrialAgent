"""Agent 执行事件：供 SSE 流式接口实时推送业务步骤（不暴露思维链）。

节点通过 emit_step 推送事件；SSE 端点通过 EventSink 收集。
"""

import contextvars
from typing import Any

_current_sink: contextvars.ContextVar["EventSink | None"] = contextvars.ContextVar(
    "agent_event_sink", default=None
)


class EventSink:
    def emit(self, event: dict[str, Any]) -> None:  # pragma: no cover - 接口定义
        raise NotImplementedError


def set_sink(sink: EventSink | None) -> None:
    _current_sink.set(sink)


def emit_event(event: dict[str, Any]) -> None:
    sink = _current_sink.get()
    if sink is not None:
        sink.emit(event)


def emit_step(
    label: str, status: str = "done", tool: str | None = None, detail: str | None = None
) -> None:
    emit_event(
        {
            "type": "step",
            "label": label,
            "status": status,
            "tool": tool,
            "detail": detail,
        }
    )

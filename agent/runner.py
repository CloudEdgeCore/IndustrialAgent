"""Agent 运行入口（P4：同步运行 + SSE 流式运行）。

SSE 事件（业务步骤，不暴露思维链）：
- {"type": "step", "label": ..., "status": "done|warning|error", "tool": ...}
- {"type": "result", "final_answer": ..., "task_type": ..., "grounding": {...}}
- {"type": "error", "message": ...}

多轮会话（P7）：``history`` 为 {role, content} 列表，随请求传入并注入 Router
与专业 Agent 的提示词；此前实现只持久化历史却从不读取，会话实际无上下文。
"""

import queue
import threading
from collections.abc import Iterator, Sequence
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from agent.events import EventSink, set_sink
from agent.graph import build_graph
from agent.llm import get_chat_model
from agent.state import AgentState


def run_agent(
    user_query: str,
    context: dict | None = None,
    model: BaseChatModel | None = None,
    session_id: str | None = None,
    agents: Sequence[str] | None = None,
    history: Sequence[dict] | None = None,
) -> AgentState:
    chat_model = model or get_chat_model()
    graph = build_graph(chat_model, agents=agents)
    initial: AgentState = {
        "session_id": session_id or str(uuid4()),
        "user_query": user_query,
        "context": context or {},
        "history": [dict(item) for item in (history or [])],
        "steps": [{"label": "分析任务", "status": "started"}],
    }
    result = graph.invoke(initial)
    if not result.get("final_answer") and result.get("agent_results"):
        result["final_answer"] = result["agent_results"][0]["conclusion"]["summary"]
    return result


def _aggregate_grounding(agent_results: list[dict]) -> dict[str, Any]:
    """汇总各专业 Agent 的数值 grounding 结果（证据可溯源性的量化信号）。"""
    reports = [item.get("grounding") for item in agent_results if item.get("grounding")]
    checked = sum(int(item.get("checked", 0)) for item in reports)
    matched = sum(int(item.get("matched", 0)) for item in reports)
    unmatched = [value for item in reports for value in item.get("unmatched", [])]
    return {
        "checked": checked,
        "matched": matched,
        "unmatched": unmatched,
        "ratio": round(matched / checked, 4) if checked else 1.0,
        "degraded_agents": [
            item.get("agent") for item in agent_results if item.get("degraded")
        ],
    }


def _result_event(result: AgentState) -> dict[str, Any]:
    report = result.get("report") or {}
    agent_results = result.get("agent_results", [])
    return {
        "type": "result",
        "session_id": result.get("session_id"),
        "task_type": result.get("task_type"),
        "agents": result.get("agents", []),
        "final_answer": result.get("final_answer", ""),
        "report_id": report.get("report_id"),
        "steps": result.get("steps", []),
        "tool_results": [
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "source": item.get("source"),
                "row_count": item.get("row_count"),
            }
            for item in result.get("tool_results", [])
        ],
        "evidence_count": len(result.get("evidence", [])),
        "grounding": _aggregate_grounding(agent_results),
    }


def run_agent_streaming(
    user_query: str,
    context: dict | None = None,
    model: BaseChatModel | None = None,
    session_id: str | None = None,
    agents: Sequence[str] | None = None,
    on_complete: Any = None,
    history: Sequence[dict] | None = None,
) -> Iterator[dict[str, Any]]:
    """在后台线程运行 Agent，流式产出事件。on_complete(result) 用于持久化。"""
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    class QueueSink(EventSink):
        def emit(self, event: dict[str, Any]) -> None:
            events.put(event)

    def worker() -> None:
        set_sink(QueueSink())
        try:
            result = run_agent(
                user_query,
                context=context,
                model=model,
                session_id=session_id,
                agents=agents,
                history=history,
            )
            if on_complete is not None:
                try:
                    on_complete(result)
                except Exception as exc:  # noqa: BLE001 - 持久化失败不阻断响应
                    events.put({"type": "warning", "message": f"会话持久化失败: {exc}"})
            events.put(_result_event(result))
        except Exception as exc:  # noqa: BLE001 - 统一转为错误事件
            events.put({"type": "error", "message": str(exc)})
        finally:
            events.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        event = events.get()
        if event is None:
            break
        yield event

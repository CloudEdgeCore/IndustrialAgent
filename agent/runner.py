"""Agent 运行入口（P4 API 层将包装为 SSE 流式接口）。"""

from collections.abc import Sequence
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel

from agent.graph import build_graph
from agent.llm import get_chat_model
from agent.state import AgentState


def run_agent(
    user_query: str,
    context: dict | None = None,
    model: BaseChatModel | None = None,
    session_id: str | None = None,
    agents: Sequence[str] = ("equipment",),
) -> AgentState:
    chat_model = model or get_chat_model()
    graph = build_graph(chat_model, agents=agents)
    initial: AgentState = {
        "session_id": session_id or str(uuid4()),
        "user_query": user_query,
        "context": context or {},
        "steps": [{"label": "分析任务", "status": "started"}],
    }
    result = graph.invoke(initial)
    if not result.get("final_answer") and result.get("agent_results"):
        result["final_answer"] = result["agent_results"][0]["conclusion"]["summary"]
    return result

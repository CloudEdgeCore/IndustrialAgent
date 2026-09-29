"""Agent 图编排（LangGraph StateGraph）。

两种模式：
- Router 模式（默认）：START → router → 条件边按 run_order 顺序执行 → END
- 固定模式（测试 / 手动指定）：按传入 agents 顺序执行
"""

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agent.equipment.agent import make_node as make_equipment_node
from agent.process.agent import make_node as make_process_node
from agent.quality.agent import make_node as make_quality_node
from agent.report.agent import make_node as make_report_node
from agent.router.agent import make_node as make_router_node
from agent.state import AgentState

NODE_FACTORIES = {
    "equipment": make_equipment_node,
    "process": make_process_node,
    "quality": make_quality_node,
    "report": make_report_node,
}
EXECUTABLE = ("equipment", "process", "quality", "report")


def _route_from_router(state: AgentState) -> str:
    order = state.get("run_order") or []
    return order[0] if order else END


def _make_route_fn(node_name: str):
    def route(state: AgentState) -> str:
        order = state.get("run_order") or []
        if node_name not in order:
            return END
        index = order.index(node_name)
        return order[index + 1] if index + 1 < len(order) else END

    return route


def build_graph(model: BaseChatModel, agents: Sequence[str] | None = None):
    graph = StateGraph(AgentState)

    if agents is not None:
        unknown = [name for name in agents if name not in NODE_FACTORIES]
        if unknown:
            raise ValueError(f"未知 Agent: {unknown}")
        if not agents:
            raise ValueError("至少需要一个 Agent")
        for name in agents:
            graph.add_node(name, NODE_FACTORIES[name](model))
        previous = START
        for name in agents:
            graph.add_edge(previous, name)
            previous = name
        graph.add_edge(previous, END)
        return graph.compile()

    graph.add_node("router", make_router_node(model))
    for name in EXECUTABLE:
        graph.add_node(name, NODE_FACTORIES[name](model))
    graph.add_edge(START, "router")

    path_map = {name: name for name in EXECUTABLE}
    path_map[END] = END
    graph.add_conditional_edges("router", _route_from_router, path_map)
    for name in EXECUTABLE:
        graph.add_conditional_edges(name, _make_route_fn(name), path_map)
    return graph.compile()

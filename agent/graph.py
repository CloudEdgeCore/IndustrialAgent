"""Agent 图编排（LangGraph StateGraph）。

当前阶段（P3 进行中）：支持任意专业 Agent 组合的顺序执行；
Router 接入后由条件边按意图选择 agents 子集。
"""

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agent.equipment.agent import make_node as make_equipment_node
from agent.process.agent import make_node as make_process_node
from agent.quality.agent import make_node as make_quality_node
from agent.state import AgentState

NODE_FACTORIES = {
    "equipment": make_equipment_node,
    "process": make_process_node,
    "quality": make_quality_node,
}


def build_graph(model: BaseChatModel, agents: Sequence[str] = ("equipment",)):
    unknown = [name for name in agents if name not in NODE_FACTORIES]
    if unknown:
        raise ValueError(f"未知 Agent: {unknown}")
    if not agents:
        raise ValueError("至少需要一个 Agent")

    graph = StateGraph(AgentState)
    for name in agents:
        graph.add_node(name, NODE_FACTORIES[name](model))

    previous = START
    for name in agents:
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()

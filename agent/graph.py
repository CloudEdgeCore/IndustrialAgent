"""Agent 图编排（LangGraph StateGraph）。

当前阶段（P3 进行中）：Equipment Agent 单节点跑通；
后续步骤按计划接入 Process / Quality / Report / Router。
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agent.equipment.agent import make_node as make_equipment_node
from agent.state import AgentState


def build_graph(model: BaseChatModel):
    graph = StateGraph(AgentState)
    graph.add_node("equipment", make_equipment_node(model))
    graph.add_edge(START, "equipment")
    graph.add_edge("equipment", END)
    return graph.compile()

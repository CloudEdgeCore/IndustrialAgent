"""Agent 状态模型（架构 §14）。"""

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_query: str
    context: dict[str, Any]  # 页面上下文：equipment_id / time_range / active_alarms
    history: list[dict]  # 多轮会话历史（role/content），供 Router 与专业 Agent 理解上下文
    task_type: str  # router 输出
    agents: list[str]  # 路由到的专业 Agent
    need_report: bool
    run_order: list[str]  # 实际执行顺序（agents + 可选 report）
    steps: Annotated[list[dict], operator.add]  # 执行步骤（UI 展示，不暴露思维链）
    tool_results: Annotated[list[dict], operator.add]  # 工具调用摘要（含来源）
    evidence: Annotated[list[dict], operator.add]  # 证据链
    agent_results: Annotated[list[dict], operator.add]  # 各专业 Agent 结论
    report: dict | None
    final_answer: str
    error: str | None

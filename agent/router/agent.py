"""Router Agent：理解意图 → 选择专业 Agent → 决定是否生成报告（PRD §6 / 架构 §5）。

LLM 路由失败时降级为关键词启发式路由（确定性兜底）。
"""

import json
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.state import AgentState

NAME = "router"

TASK_LABELS = {
    "equipment_diagnosis": "设备故障诊断",
    "process_analysis": "工艺异常分析",
    "quality_trace": "质量问题溯源",
    "knowledge_qa": "工业知识问答",
    "report": "报告生成",
    "mixed": "综合分析",
}

SYSTEM_PROMPT = """你是工业 AI 任务路由器（Router Agent），负责判断用户意图并调度专业 Agent。

只输出一个 JSON 对象（不要输出其他内容），字段：
{
  "task_type": "equipment_diagnosis | process_analysis | quality_trace |
                knowledge_qa | report | mixed",
  "agents": ["equipment" | "process" | "quality"],
  "need_report": true/false,
  "reason": "路由理由（一句话）"
}

路由规则：
- 设备故障 / 报警 / 温度 / 振动 / 停机 / 维修 → equipment
- 工艺参数 / 产线 / 压力 / 流量波动 / 阀门 → process
- 质量 / 不良率 / 缺陷 / 批次 / 裂纹 / 合格率 → quality
- 纯知识问答（报警代码解释、SOP 查询）→ knowledge_qa，agents 可为空
- 用户明确要求生成报告或问题为综合分析 → need_report 为 true
- 复合问题可同时选择多个 agents（task_type 用 mixed）"""


class RouteDecision(BaseModel):
    task_type: Literal[
        "equipment_diagnosis",
        "process_analysis",
        "quality_trace",
        "knowledge_qa",
        "report",
        "mixed",
    ]
    agents: list[Literal["equipment", "process", "quality"]] = Field(default_factory=list)
    need_report: bool = False
    reason: str = ""


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return json.loads(stripped[start : end + 1])


def heuristic_route(query: str) -> RouteDecision:
    agents: list[str] = []
    if any(k in query for k in ("设备", "报警", "温度", "振动", "主轴", "停机", "维修")):
        agents.append("equipment")
    if any(k in query for k in ("工艺", "产线", "参数", "压力", "流量", "波动", "阀门")):
        agents.append("process")
    if any(k in query for k in ("质量", "不良", "缺陷", "批次", "裂纹", "合格率")):
        agents.append("quality")
    need_report = "报告" in query or len(agents) > 1
    if len(agents) > 1:
        task_type = "mixed"
    elif agents:
        task_type = {
            "equipment": "equipment_diagnosis",
            "process": "process_analysis",
            "quality": "quality_trace",
        }[agents[0]]
    else:
        task_type = "knowledge_qa"
    return RouteDecision(
        task_type=task_type,
        agents=agents,
        need_report=need_report,
        reason="关键词启发式路由（LLM 路由不可用）",
    )


def _normalize(decision: RouteDecision) -> RouteDecision:
    if decision.task_type == "report":
        return RouteDecision(
            task_type="report", agents=[], need_report=True, reason=decision.reason
        )
    agents: list[str] = []
    for agent in decision.agents:
        if agent not in agents:
            agents.append(agent)
    if not agents:
        agents = ["equipment"]  # 知识问答由设备 Agent 承载知识检索
    return RouteDecision(
        task_type=decision.task_type,
        agents=agents,
        need_report=decision.need_report,
        reason=decision.reason,
    )


def make_node(model: BaseChatModel):
    def node(state: AgentState) -> dict[str, Any]:
        task = (
            f"用户问题：{state.get('user_query', '')}\n"
            f"页面上下文：{json.dumps(state.get('context') or {}, ensure_ascii=False)}"
        )
        try:
            response = model.invoke([SystemMessage(SYSTEM_PROMPT), HumanMessage(task)])
            decision = _normalize(
                RouteDecision.model_validate(_extract_json(str(response.content)))
            )
        except Exception:  # noqa: BLE001 - 降级为启发式路由
            decision = _normalize(heuristic_route(state.get("user_query", "")))

        run_order = list(decision.agents)
        if decision.need_report:
            run_order.append("report")

        return {
            "task_type": decision.task_type,
            "agents": list(decision.agents),
            "need_report": decision.need_report,
            "run_order": run_order,
            "steps": [
                {
                    "label": f"已识别：{TASK_LABELS[decision.task_type]}",
                    "status": "done",
                    "detail": decision.reason,
                }
            ],
        }

    return node

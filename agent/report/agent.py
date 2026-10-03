"""Report Agent：汇总各专业 Agent 结论，生成结构化报告（PRD §6）。

设计：结论合并（findings/根因/建议/风险/来源）为确定性逻辑（可追溯、不编造），
LLM 仅负责执行摘要与数据范围描述，失败时降级为确定性汇总。
"""

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.events import emit_step
from agent.state import AgentState
from tools.base import ToolContext, ToolError
from tools.executor import execute_tool
from tools.reports.models import ReportRequest, RootCauseCandidate

NAME = "report"

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_RISK_LABEL = {"low": "低", "medium": "中", "high": "高", "critical": "严重"}

SYSTEM_PROMPT = """你是报告 Agent（Report Agent），负责汇总专业 Agent 的分析结论并生成报告。

只输出一个 JSON 对象（不要输出其他内容），字段：
{
  "title": "报告标题",
  "summary": "执行摘要（2-3 句，必须包含关键数值）",
  "data_range": "数据范围说明（设备 / 时间 / 数据集）"
}
禁止编造未出现在分析结论中的数值。"""


def report_type_from_agents(agents: list[str]) -> str:
    if "equipment" in agents:
        return "equipment_diagnosis"
    if "process" in agents:
        return "process_analysis"
    if "quality" in agents:
        return "quality_analysis"
    return "daily"


def merge_report_inputs(state: AgentState) -> dict[str, Any]:
    conclusions = [
        item.get("conclusion", {}) for item in state.get("agent_results", [])
    ]
    findings: list[str] = []
    causes: list[dict] = []
    cause_seen: set[str] = set()
    recommendations: list[str] = []
    sources: list[str] = []

    for conclusion in conclusions:
        for finding in conclusion.get("findings", []):
            if finding not in findings:
                findings.append(finding)
        for candidate in conclusion.get("root_causes", []):
            if candidate["cause"] not in cause_seen:
                cause_seen.add(candidate["cause"])
                causes.append(candidate)
        for step in conclusion.get("recommendations", []):
            if step not in recommendations:
                recommendations.append(step)
        for source in conclusion.get("sources", []):
            if source not in sources:
                sources.append(source)

    for item in state.get("evidence", []):
        source = item.get("source")
        if source and source not in sources:
            sources.append(source)

    # 降级与证据校验信号必须进入报告，避免"解析失败的占位结论"被当作分析结果
    agent_results = state.get("agent_results", [])
    degraded = [item.get("agent") for item in agent_results if item.get("degraded")]
    grounding_checked = sum(
        int((item.get("grounding") or {}).get("checked", 0)) for item in agent_results
    )
    grounding_matched = sum(
        int((item.get("grounding") or {}).get("matched", 0)) for item in agent_results
    )
    unmatched = [
        value
        for item in agent_results
        for value in (item.get("grounding") or {}).get("unmatched", [])
    ]
    if degraded:
        findings.insert(
            0,
            f"注意：以下子分析未通过结构化解析（已降级为工具过程留痕），"
            f"结论需人工复核：{', '.join(str(name) for name in degraded)}。",
        )
    if grounding_checked and unmatched:
        findings.append(
            f"证据校验：{grounding_matched}/{grounding_checked} 个结论数值可在工具返回结果中"
            f"溯源；未溯源数值：{', '.join(unmatched[:8])}。"
        )

    risk = "medium"
    for conclusion in conclusions:
        level = conclusion.get("risk_level", "medium")
        if _RISK_ORDER.get(level, 1) > _RISK_ORDER[risk]:
            risk = level

    summary = "；".join(
        conclusion.get("summary", "")
        for conclusion in conclusions
        if conclusion.get("summary")
    )
    return {
        "findings": findings,
        "root_causes": causes,
        "recommendations": recommendations,
        "risk_level": risk,
        "sources": sources,
        "summary": summary,
    }


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


def make_node(model: BaseChatModel):
    def node(state: AgentState) -> dict[str, Any]:
        merged = merge_report_inputs(state)
        agents = list(state.get("agents") or [])
        report_type = report_type_from_agents(agents)

        title = "工业 AI 分析报告"
        summary = merged["summary"]
        data_range = f"基于 {len(state.get('tool_results', []))} 次工具调用结果"

        prompt_lines = [
            f"用户问题：{state.get('user_query', '')}",
            "各专业 Agent 结论：",
            json.dumps(
                [item.get("conclusion", {}) for item in state.get("agent_results", [])],
                ensure_ascii=False,
                default=str,
            ),
        ]
        try:
            response = model.invoke(
                [SystemMessage(SYSTEM_PROMPT), HumanMessage("\n".join(prompt_lines))]
            )
            parsed = _extract_json(str(response.content))
            title = parsed.get("title") or title
            summary = parsed.get("summary") or summary
            data_range = parsed.get("data_range") or data_range
        except Exception:  # noqa: BLE001 - 降级为确定性汇总
            pass

        if not summary:
            summary = "本次任务未产生专业 Agent 结论，请人工复核工具执行过程。"

        request = ReportRequest(
            report_type=report_type,
            title=title[:200],
            problem=state.get("user_query", ""),
            data_range=data_range,
            findings=merged["findings"] or [summary],
            root_causes=[RootCauseCandidate(**item) for item in merged["root_causes"]],
            recommendations=merged["recommendations"] or ["人工复核工具执行过程"],
            risk_level=merged["risk_level"],
            sources=merged["sources"] or ["tool:none"],
            equipment_id=(state.get("context") or {}).get("equipment_id"),
        )

        status = "done"
        report: dict | None = None
        try:
            result = execute_tool(
                "report.generate",
                request.model_dump(),
                ToolContext(agent=NAME, session_id=state.get("session_id")),
            )
            report = {
                "report_id": result.data["report_id"],
                "title": title,
                "risk_level": merged["risk_level"],
                "markdown": result.data["markdown"],
            }
            final_answer = (
                f"已生成报告（#{report['report_id']}）：{title}，"
                f"风险等级：{_RISK_LABEL[merged['risk_level']]}。"
            )
        except ToolError as exc:
            status = "error"
            final_answer = f"报告生成失败：{exc}"

        emit_step("生成报告", status=status, tool="report.generate")
        # 报告生成也是一次工具调用，必须进入 tool_results —— 否则证据链里看不到它，
        # 依赖 tool_results 统计"实际调用了哪些工具"的评测也会把它误判为漏调。
        tool_results = [
            {
                "tool": "report.generate",
                "args": {"report_type": report_type, "title": title},
                "status": status,
                "source": "postgres:reports",
                "row_count": 1 if report else None,
                "snippet": "",
                "error": None if status == "done" else final_answer,
            }
        ]
        return {
            "report": report,
            "tool_results": tool_results,
            "steps": [
                {"label": "生成报告", "tool": "report.generate", "status": status}
            ],
            "final_answer": final_answer,
        }

    return node

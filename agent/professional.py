"""专业 Agent 通用执行机制：工具循环 + 结构化结论（Evidence-based）。

流程（对 LLM 展示为业务步骤，不暴露思维链）：
1. 系统提示词 + 会话历史 + 用户问题/上下文 → LLM 决定调用工具；
2. 工具经 Tool Layer 权限校验执行（agent 名称作为权限主体）；
3. 工具结果回填，循环至无工具调用或达上限；
4. 追加结论指令，解析为 AgentConclusion（失败重试一次，再失败**显式标记降级**）；
5. 对结论做数值 grounding 校验（对照工具真实 payload）。
"""

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.events import emit_step
from agent.grounding import verify_grounding
from agent.history import format_history
from agent.models import AgentConclusion
from agent.settings import settings
from agent.state import AgentState
from agent.tools_binding import tool_schemas_for_agent
from tools.base import ToolContext, ToolError
from tools.executor import execute_tool

STEP_LABELS = {
    "sql.query": "查询业务数据",
    "sql.alarm_search": "查询报警信息",
    "sql.history_case": "检索历史维修记录",
    "timeseries.query": "查询设备运行数据",
    "analysis.run": "执行数据分析",
    "rag.search": "检索知识库",
    "report.generate": "生成报告",
}

_MAX_PAYLOAD_CHARS = 6000

CONCLUSION_INSTRUCTION = """基于以上工具结果，输出最终结论。
只输出一个 JSON 对象（不要输出其他内容），字段：
{
  "summary": "结论摘要（含关键数值）",
  "findings": ["异常发现（每条引用具体数据）"],
  "root_causes": [
    {"cause": "根因候选", "confidence": "high|medium|low",
     "evidence": ["证据（含数值与来源）"]}
  ],
  "recommendations": ["建议排查顺序"],
  "risk_level": "low|medium|high|critical",
  "sources": ["数据来源（工具/表/文档）"]
}
要求：所有结论必须基于工具返回的真实数据，禁止编造数值；根因候选必须附证据。"""


def parse_conclusion(text: str) -> AgentConclusion:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return AgentConclusion.model_validate(json.loads(stripped[start : end + 1]))


def _task_prompt(state: AgentState) -> str:
    parts: list[str] = []
    history = format_history(state.get("history"))
    if history:
        parts.append(history)
    parts.append(f"用户问题：{state.get('user_query', '')}")
    context = state.get("context") or {}
    if context:
        parts.append(f"页面上下文：{json.dumps(context, ensure_ascii=False)}")
    return "\n".join(parts)


def make_professional_node(agent_name: str, prompt: str, model: BaseChatModel):
    tools = tool_schemas_for_agent(agent_name)
    bound = model.bind_tools(tools) if tools else model

    def node(state: AgentState) -> dict[str, Any]:
        messages: list = [SystemMessage(prompt), HumanMessage(_task_prompt(state))]
        steps: list[dict] = []
        tool_results: list[dict] = []
        evidence: list[dict] = []
        tool_payloads: list[Any] = []

        for _ in range(settings.max_tool_iterations):
            response: AIMessage = bound.invoke(messages)
            messages.append(response)
            if not response.tool_calls:
                break
            for call in response.tool_calls:
                name = str(call["name"])
                args = call.get("args") or {}
                status = "done"
                error_text: str | None = None
                try:
                    result = execute_tool(
                        name,
                        args,
                        ToolContext(
                            agent=agent_name, session_id=state.get("session_id")
                        ),
                    )
                    content = json.dumps(result.data, ensure_ascii=False, default=str)
                    if len(content) > _MAX_PAYLOAD_CHARS:
                        content = content[:_MAX_PAYLOAD_CHARS] + '...(截断)"}'
                    source = result.meta.get("source")
                    row_count = result.meta.get("row_count")
                except ToolError as exc:
                    content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    source = None
                    row_count = None
                    status = "error"
                    error_text = str(exc)[:500]
                messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
                step = {
                    "label": STEP_LABELS.get(name, f"调用 {name}"),
                    "tool": name,
                    "status": status,
                }
                steps.append(step)
                emit_step(step["label"], status=status, tool=name)
                tool_results.append(
                    {
                        "tool": name,
                        "args": args,
                        "status": status,
                        "source": source,
                        "row_count": row_count,
                        "snippet": content[:200],
                        "error": error_text,
                    }
                )
                if status == "done":
                    evidence.append(
                        {
                            "tool": name,
                            "source": source,
                            "row_count": row_count,
                            "args": args,
                        }
                    )
                    tool_payloads.append(result.data)

        messages.append(HumanMessage(CONCLUSION_INSTRUCTION))
        conclusion: AgentConclusion | None = None
        degraded = False
        degraded_reason: str | None = None
        for _attempt in range(2):
            response = model.invoke(messages)
            try:
                conclusion = parse_conclusion(str(response.content))
                break
            except Exception:  # noqa: BLE001 - 解析失败进入重试
                messages.append(response)
                messages.append(
                    HumanMessage("上一次输出无法解析，请只输出合法 JSON 对象。")
                )
        if conclusion is None:
            # 降级结论必须可识别，否则下游无法区分"分析结果"与"解析失败占位"
            degraded = True
            degraded_reason = "结论解析失败，已保留工具执行过程供人工复核"
            conclusion = AgentConclusion(
                summary=degraded_reason,
                risk_level="medium",
                sources=[item["source"] for item in evidence if item.get("source")],
            )

        grounding = verify_grounding(
            conclusion.model_dump(),
            tool_payloads,
            user_query=state.get("user_query", ""),
        )
        if not grounding.is_reliable:
            steps.append(
                {
                    "label": f"证据校验：{len(grounding.unmatched)} 个数值未在工具结果中找到",
                    "status": "warning",
                    "tool": None,
                }
            )
            emit_step(
                f"证据校验：{len(grounding.unmatched)} 个数值未溯源",
                status="warning",
                detail="未溯源数值: " + ", ".join(grounding.unmatched[:8]),
            )

        return {
            "agent_results": [
                {
                    "agent": agent_name,
                    "conclusion": conclusion.model_dump(),
                    "degraded": degraded,
                    "degraded_reason": degraded_reason,
                    "grounding": grounding.to_dict(),
                }
            ],
            "steps": steps,
            "tool_results": tool_results,
            "evidence": evidence,
        }

    return node

"""Equipment Agent 单元测试：工具绑定 / 步骤标签 / 结论解析 / 降级（离线）。"""

import json

import pytest
from langchain_core.messages import AIMessage

from agent.equipment.agent import make_node
from agent.professional import STEP_LABELS, make_professional_node, parse_conclusion
from agent.tools_binding import tool_schemas_for_agent

VALID_CONCLUSION = {
    "summary": "主轴温度超限，冷却系统疑似效率下降。",
    "findings": ["温度末段达 91℃"],
    "root_causes": [
        {"cause": "冷却系统效率下降", "confidence": "high", "evidence": ["流量下降"]}
    ],
    "recommendations": ["检查冷却液液位"],
    "risk_level": "high",
    "sources": ["postgres:sensor_readings"],
}


def test_tool_schemas_respect_permission_matrix() -> None:
    equipment = tool_schemas_for_agent("equipment")
    names = {schema["function"]["name"] for schema in equipment}
    assert names == {
        "sql.query",
        "sql.alarm_search",
        "sql.history_case",
        "timeseries.query",
        "analysis.run",
        "rag.search",
    }
    for schema in equipment:
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"

    quality = tool_schemas_for_agent("quality")
    quality_names = {schema["function"]["name"] for schema in quality}
    assert "sql.alarm_search" not in quality_names
    assert "sql.history_case" not in quality_names

    assert tool_schemas_for_agent("router") == []


def test_step_labels_cover_all_tools() -> None:
    for tool in (
        "sql.query",
        "sql.alarm_search",
        "sql.history_case",
        "timeseries.query",
        "analysis.run",
        "rag.search",
        "report.generate",
    ):
        assert tool in STEP_LABELS


def test_parse_conclusion_plain_and_fenced() -> None:
    plain = parse_conclusion(json.dumps(VALID_CONCLUSION, ensure_ascii=False))
    assert plain.risk_level == "high"
    assert plain.root_causes[0].confidence == "high"

    fenced = parse_conclusion(
        "```json\n" + json.dumps(VALID_CONCLUSION, ensure_ascii=False) + "\n```"
    )
    assert fenced.summary == VALID_CONCLUSION["summary"]

    with pytest.raises(ValueError):
        parse_conclusion("这不是 JSON")


def test_missing_evidence_rejected() -> None:
    bad = {**VALID_CONCLUSION, "root_causes": [{"cause": "x", "confidence": "high"}]}
    with pytest.raises(ValueError):
        parse_conclusion(json.dumps(bad, ensure_ascii=False))


def test_node_falls_back_when_conclusion_unparsable(scripted_llm) -> None:
    model = scripted_llm(
        [
            AIMessage(content="（无工具调用）"),
            AIMessage(content="不是 JSON"),
            AIMessage(content="还是不是 JSON"),
        ]
    )
    node = make_professional_node("equipment", "你是设备 Agent", model)
    result = node({"user_query": "测试", "session_id": "s-1"})
    conclusion = result["agent_results"][0]["conclusion"]
    assert "解析失败" in conclusion["summary"]
    assert conclusion["risk_level"] == "medium"


def test_equipment_node_factory(scripted_llm) -> None:
    model = scripted_llm(
        [
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(VALID_CONCLUSION, ensure_ascii=False)),
        ]
    )
    node = make_node(model)
    result = node({"user_query": "EQ-003 温度异常", "session_id": "s-1"})
    assert result["agent_results"][0]["agent"] == "equipment"
    assert result["agent_results"][0]["conclusion"]["risk_level"] == "high"

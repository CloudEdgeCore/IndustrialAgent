"""Process / Quality Agent 单元测试：工具绑定 / 节点工厂 / 多 Agent 链（离线）。"""

import json

from langchain_core.messages import AIMessage

from agent.process.agent import make_node as make_process_node
from agent.quality.agent import make_node as make_quality_node
from agent.runner import run_agent
from agent.tools_binding import tool_schemas_for_agent

CONCLUSION = {
    "summary": "测试结论。",
    "findings": ["发现 A"],
    "root_causes": [
        {"cause": "原因 X", "confidence": "medium", "evidence": ["证据 1"]}
    ],
    "recommendations": ["建议 1"],
    "risk_level": "medium",
    "sources": ["postgres:test"],
}


def test_process_quality_tool_schemas() -> None:
    expected = {"sql.query", "timeseries.query", "analysis.run", "rag.search"}
    for agent_name in ("process", "quality"):
        names = {
            schema["function"]["name"]
            for schema in tool_schemas_for_agent(agent_name)
        }
        assert names == expected, agent_name


def test_process_node_factory(scripted_llm) -> None:
    model = scripted_llm(
        [
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
        ]
    )
    node = make_process_node(model)
    result = node({"user_query": "2 号产线压力波动", "session_id": "s-1"})
    assert result["agent_results"][0]["agent"] == "process"
    assert result["agent_results"][0]["conclusion"]["summary"] == "测试结论。"


def test_quality_node_factory(scripted_llm) -> None:
    model = scripted_llm(
        [
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
        ]
    )
    node = make_quality_node(model)
    result = node({"user_query": "不良率升高原因", "session_id": "s-1"})
    assert result["agent_results"][0]["agent"] == "quality"


def test_multi_agent_chain_runs_in_order(scripted_llm) -> None:
    model = scripted_llm(
        [
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
        ]
    )
    result = run_agent(
        "综合分析任务", model=model, agents=("process", "quality")
    )
    assert [item["agent"] for item in result["agent_results"]] == [
        "process",
        "quality",
    ]
    assert result["final_answer"] == "测试结论。"


def test_unknown_agent_rejected(scripted_llm) -> None:
    model = scripted_llm([])
    import pytest

    with pytest.raises(ValueError, match="未知 Agent"):
        run_agent("x", model=model, agents=("equipment", "unknown"))

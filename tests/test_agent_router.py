"""Router Agent 单元测试：路由决策 / 启发式降级 / 全图条件边（离线）。"""

import json

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from agent.router.agent import (
    RouteDecision,
    _normalize,
    heuristic_route,
    make_node,
)
from agent.runner import run_agent

CONCLUSION = {
    "summary": "测试结论。",
    "findings": ["发现 A"],
    "root_causes": [{"cause": "原因 X", "confidence": "medium", "evidence": ["证据 1"]}],
    "recommendations": ["建议 1"],
    "risk_level": "medium",
    "sources": ["postgres:test"],
}


def test_route_decision_validation() -> None:
    with pytest.raises(ValidationError):
        RouteDecision.model_validate({"task_type": "unknown_type"})
    with pytest.raises(ValidationError):
        RouteDecision.model_validate(
            {"task_type": "mixed", "agents": ["hacker_agent"]}
        )


def test_normalize_rules() -> None:
    report = _normalize(
        RouteDecision(task_type="report", agents=["equipment"], need_report=True)
    )
    assert report.agents == []
    assert report.need_report is True

    empty = _normalize(RouteDecision(task_type="knowledge_qa", agents=[]))
    assert empty.agents == ["equipment"]

    deduped = _normalize(
        RouteDecision(
            task_type="mixed",
            agents=["quality", "equipment", "quality"],
        )
    )
    assert deduped.agents == ["quality", "equipment"]


def test_heuristic_route_cases() -> None:
    assert heuristic_route("3 号设备主轴温度超过 85℃").agents == ["equipment"]
    assert heuristic_route("分析 2 号产线压力波动").agents == ["process"]
    assert heuristic_route("A 产品不良率升高").agents == ["quality"]

    mixed = heuristic_route("设备温度异常且不良率升高，请生成报告")
    assert mixed.task_type == "mixed"
    assert mixed.agents == ["equipment", "quality"]
    assert mixed.need_report is True

    knowledge = heuristic_route("什么是 SPC 控制图")
    assert knowledge.task_type == "knowledge_qa"
    assert knowledge.agents == []

    alarm_question = heuristic_route("E102 是什么报警")
    assert alarm_question.task_type == "knowledge_qa"
    assert alarm_question.agents == []

    report = heuristic_route("帮我生成一份生产日报")
    assert report.task_type == "report"
    assert report.need_report is True


def test_router_node_with_llm_decision(scripted_llm) -> None:
    decision = {
        "task_type": "equipment_diagnosis",
        "agents": ["equipment"],
        "need_report": True,
        "reason": "涉及设备温度与报警",
    }
    model = scripted_llm([AIMessage(content=json.dumps(decision, ensure_ascii=False))])
    node = make_node(model)
    result = node({"user_query": "3 号设备温度异常", "context": {}})
    assert result["task_type"] == "equipment_diagnosis"
    assert result["run_order"] == ["equipment", "report"]
    assert result["steps"][0]["label"] == "已识别：设备故障诊断"


def test_router_node_falls_back_on_bad_output(scripted_llm) -> None:
    model = scripted_llm([AIMessage(content="这不是 JSON")])
    node = make_node(model)
    result = node({"user_query": "A 产品不良率为什么升高", "context": {}})
    assert result["task_type"] == "quality_trace"
    assert result["agents"] == ["quality"]


def test_router_mode_graph_end_to_end(scripted_llm) -> None:
    decision = {
        "task_type": "mixed",
        "agents": ["equipment", "quality"],
        "need_report": False,
        "reason": "复合问题",
    }
    model = scripted_llm(
        [
            AIMessage(content=json.dumps(decision, ensure_ascii=False)),
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
            AIMessage(content="无需工具"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
        ]
    )
    result = run_agent("设备温度异常且不良率升高", model=model)

    assert result["task_type"] == "mixed"
    assert result["run_order"] == ["equipment", "quality"]
    assert [item["agent"] for item in result["agent_results"]] == [
        "equipment",
        "quality",
    ]
    labels = [step["label"] for step in result["steps"]]
    assert "已识别：综合分析" in labels
    assert labels[1] == "已识别：综合分析"

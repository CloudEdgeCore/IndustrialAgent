"""Report Agent 单元测试：结论合并 / 类型映射 / JSON 提取（离线）。"""

import pytest

from agent.report.agent import (
    _extract_json,
    merge_report_inputs,
    report_type_from_agents,
)

STATE = {
    "user_query": "3 号设备温度异常",
    "agent_results": [
        {
            "agent": "equipment",
            "conclusion": {
                "summary": "主轴温度超限，冷却系统疑似效率下降。",
                "findings": ["温度末段达 92℃", "流量下降 18%"],
                "root_causes": [
                    {
                        "cause": "冷却系统效率下降",
                        "confidence": "high",
                        "evidence": ["流量下降"],
                    }
                ],
                "recommendations": ["检查冷却液液位", "更换过滤器"],
                "risk_level": "high",
                "sources": ["postgres:sensor_readings"],
            },
        },
        {
            "agent": "quality",
            "conclusion": {
                "summary": "不良率升高集中于同设备。",
                "findings": ["表面裂纹占比 54%"],
                "root_causes": [
                    {
                        "cause": "冷却系统效率下降",
                        "confidence": "medium",
                        "evidence": ["同设备不良集中"],
                    },
                    {
                        "cause": "刀具磨损",
                        "confidence": "low",
                        "evidence": ["尺寸偏差占比 15%"],
                    },
                ],
                "recommendations": ["启动根因分析"],
                "risk_level": "critical",
                "sources": ["postgres:quality_inspections"],
            },
        },
    ],
    "evidence": [
        {"tool": "timeseries.query", "source": "postgres:sensor_readings"},
        {"tool": "rag.search", "source": "postgres:document_chunks"},
    ],
}


def test_merge_report_inputs() -> None:
    merged = merge_report_inputs(STATE)
    assert merged["findings"] == ["温度末段达 92℃", "流量下降 18%", "表面裂纹占比 54%"]
    assert [item["cause"] for item in merged["root_causes"]] == [
        "冷却系统效率下降",
        "刀具磨损",
    ]
    assert merged["recommendations"] == ["检查冷却液液位", "更换过滤器", "启动根因分析"]
    assert merged["risk_level"] == "critical"
    assert merged["sources"] == [
        "postgres:sensor_readings",
        "postgres:quality_inspections",
        "postgres:document_chunks",
    ]
    assert "主轴温度超限" in merged["summary"]


def test_merge_without_conclusions() -> None:
    merged = merge_report_inputs({"agent_results": [], "evidence": []})
    assert merged["findings"] == []
    assert merged["risk_level"] == "medium"
    assert merged["summary"] == ""


def test_report_type_from_agents() -> None:
    assert report_type_from_agents(["equipment", "report"]) == "equipment_diagnosis"
    assert report_type_from_agents(["process"]) == "process_analysis"
    assert report_type_from_agents(["quality"]) == "quality_analysis"
    assert report_type_from_agents(["report"]) == "daily"


def test_extract_json() -> None:
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    with pytest.raises(ValueError):
        _extract_json("没有 JSON")

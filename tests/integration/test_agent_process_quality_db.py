"""Process / Quality Agent 集成测试：真实工具链路（工艺/质量场景 B、C）。"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from langchain_core.messages import AIMessage

from agent.runner import run_agent
from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.settings import settings

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"

PROCESS_CONCLUSION = {
    "summary": "LINE-2 压力在 15:20-16:05 波动放大，与阀门开度变化高度相关。",
    "findings": ["压力波动幅度显著高于基线", "压力与阀门开度相关性超过 0.9"],
    "root_causes": [
        {
            "cause": "阀门开度异常调节",
            "confidence": "high",
            "evidence": ["压力-阀门相关系数 0.93", "异常窗口波动 std 显著放大"],
        }
    ],
    "recommendations": ["检查阀门控制信号", "核查 PLC 参数"],
    "risk_level": "medium",
    "sources": ["postgres:process_parameters"],
}

QUALITY_CONCLUSION = {
    "summary": "A 产品近 3 天不良率约 4.6%，集中于 EQ-003 与表面裂纹缺陷。",
    "findings": ["不良率较基线明显升高", "表面裂纹为最主要缺陷"],
    "root_causes": [
        {
            "cause": "EQ-003 设备状态劣化导致表面裂纹",
            "confidence": "high",
            "evidence": ["不良集中于 EQ-003", "该设备存在温度异常与 E102 报警"],
        }
    ],
    "recommendations": ["检查 EQ-003 主轴与冷却系统", "按质量规范启动根因分析"],
    "risk_level": "high",
    "sources": ["postgres:quality_inspections", "knowledge:质量检验规范"],
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("缺少 manifest.json，先执行 python -m data.simulator")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def require_seeded_db() -> None:
    load_all_tools()
    url = normalize_database_url(
        os.environ.get("TOOL_DATABASE_URL", settings.tool_database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM process_parameters")
            if cur.fetchone()[0] == 0:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def _series(entity: str, metric: str, start: datetime, end: datetime) -> list[float]:
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "process",
            "entity_id": entity,
            "metric": metric,
            "op": "series",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        ToolContext(agent="process"),
    )
    return [row["value"] for row in result.data]


def test_process_agent_end_to_end(manifest: dict, scripted_llm) -> None:
    scenario = manifest["scenarios"]["line_pressure"]
    start = datetime.fromisoformat(scenario["window_start"])
    end = datetime.fromisoformat(scenario["window_end"])
    pressure = _series("LINE-2", "pressure", start, end)
    valve = _series("LINE-2", "valve_opening", start, end)
    assert len(pressure) == len(valve) > 30

    model = scripted_llm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "timeseries.query",
                        "args": {
                            "kind": "process",
                            "entity_id": "LINE-2",
                            "metric": "pressure",
                            "op": "series",
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                        },
                        "id": "call_1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "analysis.run",
                        "args": {
                            "op": "correlation",
                            "x": pressure,
                            "y": valve,
                            "method": "pearson",
                        },
                        "id": "call_2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rag.search",
                        "args": {"query": "液压压力波动 阀门", "top_k": 2},
                        "id": "call_3",
                    }
                ],
            ),
            AIMessage(content="工具结果已收集完毕。"),
            AIMessage(content=json.dumps(PROCESS_CONCLUSION, ensure_ascii=False)),
        ]
    )

    result = run_agent(
        "帮我分析昨天 2 号产线压力波动异常的原因。",
        context={"line_id": "LINE-2"},
        model=model,
        agents=("process",),
    )

    assert [item["agent"] for item in result["agent_results"]] == ["process"]
    tools_used = [entry["tool"] for entry in result["tool_results"]]
    assert tools_used == ["timeseries.query", "analysis.run", "rag.search"]

    correlation_entry = result["tool_results"][1]
    assert '"r": 0.9' in correlation_entry["snippet"], "相关性应基于真实数据计算"

    conclusion = result["agent_results"][0]["conclusion"]
    assert conclusion["risk_level"] == "medium"
    assert result["final_answer"].startswith("LINE-2")


def test_quality_agent_end_to_end(manifest: dict, scripted_llm) -> None:
    anchor = datetime.fromisoformat(manifest["anchor"])
    day0 = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_start = day0 - timedelta(days=2)

    model = scripted_llm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "sql.query",
                        "args": {
                            "dataset": "quality_inspections",
                            "filters": [{"field": "result", "op": "=", "value": "fail"}],
                            "group_by": ["defect_type"],
                            "time_range": {
                                "start": recent_start.isoformat(),
                                "end": anchor.isoformat(),
                            },
                        },
                        "id": "call_1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "sql.query",
                        "args": {
                            "dataset": "quality_inspections",
                            "filters": [
                                {"field": "result", "op": "=", "value": "fail"},
                                {"field": "product_id", "op": "=", "value": "PRD-A"},
                            ],
                            "group_by": ["equipment_id"],
                            "time_range": {
                                "start": recent_start.isoformat(),
                                "end": anchor.isoformat(),
                            },
                        },
                        "id": "call_2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rag.search",
                        "args": {"query": "表面裂纹 判定标准", "top_k": 2},
                        "id": "call_3",
                    }
                ],
            ),
            AIMessage(content="工具结果已收集完毕。"),
            AIMessage(content=json.dumps(QUALITY_CONCLUSION, ensure_ascii=False)),
        ]
    )

    result = run_agent(
        "最近 3 天 A 产品不良率为什么从 1.8% 升到 4.6%？",
        context={"product_id": "PRD-A"},
        model=model,
        agents=("quality",),
    )

    assert [item["agent"] for item in result["agent_results"]] == ["quality"]
    defect_entry = result["tool_results"][0]
    assert "surface_crack" in defect_entry["snippet"]
    equipment_entry = result["tool_results"][1]
    assert "EQ-003" in equipment_entry["snippet"]

    conclusion = result["agent_results"][0]["conclusion"]
    assert conclusion["risk_level"] == "high"

"""Equipment Agent 集成测试：真实工具链路（TimeSeries/报警/RAG）+ 图执行。"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from langchain_core.messages import AIMessage

from agent.runner import run_agent
from tools.db import normalize_database_url
from tools.settings import settings

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"

CONCLUSION = {
    "summary": (
        "EQ-003 主轴温度末段达 91℃，伴随冷却液流量下降与 E102 活跃报警，"
        "判断为冷却系统效率下降。"
    ),
    "findings": ["主轴温度持续超过 85℃", "冷却液流量下降"],
    "root_causes": [
        {
            "cause": "冷却系统效率下降（过滤器堵塞可能）",
            "confidence": "high",
            "evidence": [
                "近 1 小时温度最高值超过 88℃",
                "E102 为活跃报警",
                "SOP 指出流量下降优先检查过滤器",
            ],
        }
    ],
    "recommendations": ["检查冷却液液位", "检查冷却泵", "更换过滤器"],
    "risk_level": "high",
    "sources": ["postgres:sensor_readings", "postgres:alarms", "knowledge:E102 SOP"],
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("缺少 manifest.json，先执行 python -m data.simulator")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def require_seeded_db() -> None:
    url = normalize_database_url(
        os.environ.get("TOOL_DATABASE_URL", settings.tool_database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sensor_readings")
            if cur.fetchone()[0] == 0:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def test_equipment_agent_end_to_end(manifest: dict, scripted_llm) -> None:
    scenario = manifest["scenarios"]["equipment_temperature"]
    start = datetime.fromisoformat(scenario["window_start"]) - timedelta(minutes=5)
    end = datetime.fromisoformat(scenario["window_end"])

    model = scripted_llm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "timeseries.query",
                        "args": {
                            "kind": "sensor",
                            "entity_id": "EQ-003",
                            "metric": "temperature",
                            "op": "stats",
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
                        "name": "sql.alarm_search",
                        "args": {"mode": "lookup", "alarm_code": "E102"},
                        "id": "call_2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rag.search",
                        "args": {"query": "E102 处理流程", "top_k": 2},
                        "id": "call_3",
                    }
                ],
            ),
            AIMessage(content="工具结果已收集完毕。"),
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
        ]
    )

    result = run_agent(
        "3 号设备主轴温度连续超过 85℃，同时出现 E102 报警，帮我分析原因。",
        context={"equipment_id": "EQ-003"},
        model=model,
        agents=("equipment",),
    )

    labels = [step["label"] for step in result["steps"]]
    assert "查询设备运行数据" in labels
    assert "查询报警信息" in labels
    assert "检索知识库" in labels
    assert all(step["status"] == "done" for step in result["steps"] if step.get("tool"))

    assert len(result["tool_results"]) == 3
    stats_entry = result["tool_results"][0]
    assert stats_entry["source"] == "postgres:sensor_readings"
    assert '"max_value": 9' in stats_entry["snippet"]

    alarm_entry = result["tool_results"][1]
    assert alarm_entry["source"] == "fixtures:alarm_catalog"

    rag_entry = result["tool_results"][2]
    assert rag_entry["source"] == "postgres:document_chunks"

    assert len(result["evidence"]) == 3
    conclusion = result["agent_results"][0]["conclusion"]
    assert result["agent_results"][0]["agent"] == "equipment"
    assert conclusion["risk_level"] == "high"
    assert conclusion["root_causes"][0]["confidence"] == "high"
    assert result["final_answer"].startswith("EQ-003")

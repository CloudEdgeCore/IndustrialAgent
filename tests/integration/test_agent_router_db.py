"""Router Agent 集成测试：Router → Equipment（真实工具）→ Report 全链路。"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from langchain_core.messages import AIMessage

from agent.runner import run_agent
from tools.db import normalize_database_url
from tools.loader import load_all_tools
from tools.settings import settings

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"

ROUTER_DECISION = {
    "task_type": "equipment_diagnosis",
    "agents": ["equipment"],
    "need_report": True,
    "reason": "涉及主轴温度与 E102 报警，需生成诊断报告",
}

EQUIPMENT_CONCLUSION = {
    "summary": "EQ-003 主轴温度末段达 92℃，冷却液流量下降，判断为冷却系统效率下降。",
    "findings": ["主轴温度持续超过 85℃"],
    "root_causes": [
        {
            "cause": "冷却系统效率下降",
            "confidence": "high",
            "evidence": ["温度最高值超过 88℃", "E102 活跃报警"],
        }
    ],
    "recommendations": ["检查冷却液液位", "更换过滤器"],
    "risk_level": "high",
    "sources": ["postgres:sensor_readings", "postgres:alarms"],
}

REPORT_SUMMARY = {
    "title": "EQ-003 主轴温度异常诊断报告",
    "summary": "EQ-003 主轴温度末段达 92℃ 且冷却液流量下降，判定为冷却系统效率下降导致。",
    "data_range": "EQ-003 近 1 小时温度时序 + 报警记录 + 知识库 SOP",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip("缺少 manifest.json，先执行 python -m data.simulator")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def require_seeded_db() -> None:
    load_all_tools()
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
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


def test_full_router_equipment_report_pipeline(manifest: dict, scripted_llm) -> None:
    scenario = manifest["scenarios"]["equipment_temperature"]
    start = datetime.fromisoformat(scenario["window_start"]) - timedelta(minutes=5)
    end = datetime.fromisoformat(scenario["window_end"])

    model = scripted_llm(
        [
            AIMessage(content=json.dumps(ROUTER_DECISION, ensure_ascii=False)),
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
            AIMessage(content="工具结果已收集完毕。"),
            AIMessage(content=json.dumps(EQUIPMENT_CONCLUSION, ensure_ascii=False)),
            AIMessage(content=json.dumps(REPORT_SUMMARY, ensure_ascii=False)),
        ]
    )

    result = run_agent(
        "3 号设备主轴温度超过 85℃，出现 E102 报警，帮我分析并生成报告。",
        context={"equipment_id": "EQ-003"},
        model=model,
    )

    assert result["task_type"] == "equipment_diagnosis"
    assert result["run_order"] == ["equipment", "report"]
    labels = [step["label"] for step in result["steps"]]
    assert labels[1] == "已识别：设备故障诊断"
    assert "查询设备运行数据" in labels
    assert "生成报告" in labels

    assert result["tool_results"][0]["source"] == "postgres:sensor_readings"
    assert '"max_value": 9' in result["tool_results"][0]["snippet"]

    report = result["report"]
    assert report is not None
    assert report["report_id"] >= 1
    assert result["final_answer"].startswith("已生成报告")

    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, risk_level FROM reports WHERE report_id = %s",
                (report["report_id"],),
            )
            row = cur.fetchone()
    assert row == (REPORT_SUMMARY["title"], "high")

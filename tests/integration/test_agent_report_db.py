"""Report Agent 集成测试：多 Agent 链 + 报告落库（无库自动跳过）。"""

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


def test_equipment_then_report_chain(manifest: dict, scripted_llm) -> None:
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
            AIMessage(content="工具结果已收集完毕。"),
            AIMessage(content=json.dumps(EQUIPMENT_CONCLUSION, ensure_ascii=False)),
            AIMessage(content=json.dumps(REPORT_SUMMARY, ensure_ascii=False)),
        ]
    )

    result = run_agent(
        "3 号设备主轴温度超过 85℃，出现 E102 报警，帮我分析并生成报告。",
        context={"equipment_id": "EQ-003"},
        model=model,
        agents=("equipment", "report"),
    )

    assert [item["agent"] for item in result["agent_results"]] == ["equipment"]
    report = result["report"]
    assert report is not None
    assert report["report_id"] >= 1
    assert report["title"] == REPORT_SUMMARY["title"]
    assert "## 四、根因候选" in report["markdown"]
    assert "风险等级：高" in report["markdown"]
    assert "冷却系统效率下降" in report["markdown"]

    labels = [step["label"] for step in result["steps"]]
    assert "生成报告" in labels
    report_step = next(step for step in result["steps"] if step["label"] == "生成报告")
    assert report_step["status"] == "done"
    assert result["final_answer"].startswith("已生成报告")

    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, risk_level, status, created_by FROM reports "
                "WHERE report_id = %s",
                (report["report_id"],),
            )
            row = cur.fetchone()
    assert row == (REPORT_SUMMARY["title"], "high", "draft", "AI")


def test_report_only_run_with_fallback(scripted_llm) -> None:
    model = scripted_llm([AIMessage(content="无法生成 JSON")])
    result = run_agent("生成一份当前状态报告", model=model, agents=("report",))

    report = result["report"]
    assert report is not None
    assert report["risk_level"] == "medium"
    assert "未产生专业 Agent 结论" in report["markdown"]

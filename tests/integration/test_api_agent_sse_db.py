"""SSE Agent 流式接口集成测试：事件顺序 + 会话持久化（无库自动跳过）。"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app
from tools.db import normalize_database_url
from tools.loader import load_all_tools
from tools.settings import settings

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"

ROUTER_DECISION = {
    "task_type": "equipment_diagnosis",
    "agents": ["equipment"],
    "need_report": True,
    "reason": "设备温度与报警，需生成报告",
}
CONCLUSION = {
    "summary": "EQ-003 主轴温度末段达 92℃，判断为冷却系统效率下降。",
    "findings": ["主轴温度持续超过 85℃"],
    "root_causes": [
        {
            "cause": "冷却系统效率下降",
            "confidence": "high",
            "evidence": ["温度最高值超过 88℃"],
        }
    ],
    "recommendations": ["检查冷却液液位"],
    "risk_level": "high",
    "sources": ["postgres:sensor_readings"],
}
REPORT_SUMMARY = {
    "title": "EQ-003 温度异常诊断报告（SSE 测试）",
    "summary": "EQ-003 主轴温度末段达 92℃。",
    "data_range": "EQ-003 近 1 小时",
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


@pytest.fixture(scope="module")
def auth_headers() -> dict:
    client = TestClient(app)
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _collect_events(client: TestClient, payload: dict, headers: dict) -> list[dict]:
    events: list[dict] = []
    with client.stream("POST", "/agent/chat", json=payload, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def test_agent_chat_streams_steps_then_result(
    manifest: dict, scripted_llm, auth_headers: dict
) -> None:
    scenario = manifest["scenarios"]["equipment_temperature"]
    start = datetime.fromisoformat(scenario["window_start"]) - timedelta(minutes=5)
    end = datetime.fromisoformat(scenario["window_end"])

    app.state.agent_model = scripted_llm(
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
            AIMessage(content=json.dumps(CONCLUSION, ensure_ascii=False)),
            AIMessage(content=json.dumps(REPORT_SUMMARY, ensure_ascii=False)),
        ]
    )
    try:
        client = TestClient(app)
        events = _collect_events(
            client,
            {
                "query": "3 号设备主轴温度超过 85℃，出现 E102 报警，帮我分析并生成报告。",
                "context": {"equipment_id": "EQ-003"},
            },
            auth_headers,
        )
    finally:
        del app.state.agent_model

    types = [event["type"] for event in events]
    assert types[-1] == "result"
    assert "error" not in types

    step_labels = [event["label"] for event in events if event["type"] == "step"]
    assert step_labels[0] == "分析任务"
    assert step_labels[1] == "已识别：设备故障诊断"
    assert "查询设备运行数据" in step_labels
    assert step_labels[-1] == "生成报告"
    assert step_labels.index("查询设备运行数据") < step_labels.index("生成报告")

    result = events[-1]
    assert result["task_type"] == "equipment_diagnosis"
    assert result["report_id"] >= 1
    assert result["final_answer"].startswith("已生成报告")
    assert result["tool_results"][0]["status"] == "done"
    assert result["evidence_count"] == 1
    session_id = result["session_id"]

    messages = client.get(
        f"/agent/sessions/{session_id}/messages", headers=auth_headers
    ).json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "已生成报告" in messages[1]["content"]


def test_agent_chat_reports_error_event(scripted_llm, auth_headers: dict) -> None:
    app.state.agent_model = scripted_llm([])
    try:
        client = TestClient(app)
        events = _collect_events(client, {"query": "测试错误路径"}, auth_headers)
    finally:
        del app.state.agent_model

    assert events[-1]["type"] == "error"

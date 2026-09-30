"""REST API 集成测试（无库自动跳过）。"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.settings import settings

pytestmark = pytest.mark.integration

client = TestClient(app)


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
            cur.execute("SELECT count(*) FROM equipment")
            if cur.fetchone()[0] == 0:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def test_equipment_list_and_filters() -> None:
    response = client.get("/equipment")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 30

    alarms = client.get("/equipment", params={"status": "alarm"}).json()
    assert alarms["total"] >= 1
    assert any(item["equipment_id"] == "EQ-003" for item in alarms["items"])

    cnc = client.get("/equipment", params={"equipment_type": "cnc"}).json()
    assert cnc["total"] == 12


def test_equipment_detail_with_alarm_and_readings() -> None:
    response = client.get("/equipment/EQ-003")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alarm"
    assert any(alarm["alarm_code"] == "E102" for alarm in body["active_alarms"])
    assert "temperature" in body["latest_readings"]

    missing = client.get("/equipment/EQ-999")
    assert missing.status_code == 404


def test_quality_summary_scenario_b() -> None:
    response = client.get("/quality/summary", params={"product_id": "PRD-A", "days": 3})
    assert response.status_code == 200
    body = response.json()
    assert 0.03 <= body["fail_rate"] <= 0.06, body
    assert body["baseline_fail_rate"] < 0.03
    assert body["top_defects"][0]["defect_type"] == "surface_crack"
    assert any(item["equipment_id"] == "EQ-003" for item in body["by_equipment"])


def test_inspections_list() -> None:
    response = client.get(
        "/quality/inspections", params={"product_id": "PRD-A", "result": "fail", "limit": 10}
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 10
    assert all(item["result"] == "fail" for item in items)


def test_knowledge_documents_and_search() -> None:
    documents = client.get("/knowledge/documents").json()
    assert len(documents) >= 6
    assert all(doc["chunk_count"] > 0 for doc in documents)

    response = client.post(
        "/knowledge/search", json={"query": "E102 怎么处理", "top_k": 3}
    )
    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 3
    assert "E102" in hits[0]["content"]
    assert hits[0]["document_title"]


def test_quality_trend_series() -> None:
    response = client.get("/quality/trend", params={"product_id": "PRD-A", "days": 7})
    assert response.status_code == 200
    points = response.json()
    assert len(points) >= 5
    assert all(point["total"] > 0 for point in points)
    recent = points[-3:]
    assert all(point["fail_rate"] >= 0.03 for point in recent), recent


def test_alarms_list_with_equipment_name() -> None:
    response = client.get("/alarms", params={"status": "active", "limit": 20})
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    assert all("equipment_name" in item for item in items)
    assert any(item["alarm_code"] == "E102" for item in items)

    eq3 = client.get("/alarms", params={"equipment_id": "EQ-003"}).json()
    assert all(item["equipment_id"] == "EQ-003" for item in eq3)


def test_equipment_readings_series() -> None:
    response = client.get(
        "/equipment/EQ-003/readings",
        params={"sensor_type": "temperature", "hours": 2, "bucket": "5m"},
    )
    assert response.status_code == 200
    points = response.json()
    assert len(points) >= 12
    assert max(point["value"] for point in points) > 88
    assert points[0]["timestamp"] < points[-1]["timestamp"]

    assert (
        client.get(
            "/equipment/EQ-003/readings", params={"sensor_type": "hack"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/equipment/EQ-999/readings", params={"sensor_type": "temperature"}
        ).status_code
        == 404
    )


def test_equipment_maintenance_records() -> None:
    response = client.get("/equipment/EQ-003/maintenance")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    assert any(item["root_cause"] == "冷却过滤器堵塞" for item in items)
    assert all(item["equipment_id"] == "EQ-003" for item in items)


def test_reports_list_and_detail() -> None:
    created = execute_tool(
        "report.generate",
        {
            "report_type": "equipment_diagnosis",
            "title": "API 测试报告",
            "problem": "测试",
            "data_range": "测试范围",
            "findings": ["测试发现"],
            "root_causes": [],
            "recommendations": ["测试建议"],
            "risk_level": "medium",
            "sources": ["test"],
        },
        ToolContext(agent="report"),
    )
    report_id = created.data["report_id"]

    listing = client.get("/reports", params={"limit": 5}).json()
    assert listing["total"] >= 1
    assert listing["items"][0]["report_id"] >= report_id

    detail = client.get(f"/reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "API 测试报告"
    assert "## 一、问题概述" in detail.json()["content_markdown"]

    export = client.get(f"/reports/{report_id}/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown")
    assert "attachment" in export.headers["content-disposition"]
    assert "## 四、根因候选" in export.text

    assert client.get("/reports/999999").status_code == 404

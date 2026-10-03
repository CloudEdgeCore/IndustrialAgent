"""数据新鲜度 / 窗口锚点集成测试（无库自动跳过）。

回归防护：这些断言在"窗口锚定 datetime.now()"的旧实现下会随时间推移失败
（数据落库数天后 "last_24h" 滑出数据集）。锚定数据末尾后恒定成立。
"""

import os
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.freshness import data_freshness, reset_cache
from tools.loader import load_all_tools
from tools.settings import settings

pytestmark = pytest.mark.integration

client = TestClient(app)
EQUIPMENT_CTX = ToolContext(agent="equipment")


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
            cur.execute("SELECT max(timestamp) FROM sensor_readings")
            if cur.fetchone()[0] is None:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()
    reset_cache()


@pytest.fixture
def db_max_sensor_time() -> datetime:
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT max(timestamp) FROM sensor_readings")
        return cur.fetchone()[0]


def test_anchor_equals_latest_data_timestamp(db_max_sensor_time: datetime) -> None:
    report = data_freshness(force_refresh=True)
    assert report.resolved_from == "data"
    assert report.anchor == db_max_sensor_time


def test_meta_freshness_endpoint(db_max_sensor_time: datetime) -> None:
    response = client.get("/meta/freshness")
    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["anchor"]) == db_max_sensor_time
    assert body["resolved_from"] == "data"
    assert body["lag_hours"] >= 0
    assert body["domains"]["equipment"] is not None


def test_relative_window_lands_on_data_not_wall_clock() -> None:
    """回归：相对时间窗口必须命中数据（旧实现在数据陈旧时返回 0 行）。"""
    reset_cache()
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "sensor",
            "entity_id": "EQ-003",
            "metric": "temperature",
            "op": "stats",
            "relative": "last_24h",
        },
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 1
    assert result.meta["window"]["anchor_source"] == "data"
    assert datetime.fromisoformat(result.meta["range"]["end"]) == data_freshness().anchor


def test_sql_query_relative_window_hits_data() -> None:
    reset_cache()
    result = execute_tool(
        "sql.query",
        {
            "dataset": "alarms",
            "filters": [{"field": "equipment_id", "op": "=", "value": "EQ-003"}],
            "time_range": {"relative": "last_24h"},
        },
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 1
    assert result.meta["window"]["anchor_source"] == "data"


def test_quality_summary_is_anchored_and_reproduces_scenario() -> None:
    """PRD 场景 B 的可复现性不依赖数据落库时间。"""
    reset_cache()
    body = client.get(
        "/quality/summary", params={"product_id": "PRD-A", "days": 3}
    ).json()
    assert datetime.fromisoformat(body["data_as_of"]) == data_freshness().anchor
    assert body["anchor_source"] == "data"
    assert body["fail_rate"] > (body["baseline_fail_rate"] or 0)
    assert body["top_defects"][0]["defect_type"] == "surface_crack"
    assert any(item["equipment_id"] == "EQ-003" for item in body["by_equipment"])


def test_quality_trend_is_anchored() -> None:
    reset_cache()
    body = client.get("/quality/trend", params={"product_id": "PRD-A", "days": 14}).json()
    assert body, "锚定数据末尾后趋势不应为空"
    last_day = datetime.fromisoformat(body[-1]["date"]).replace(tzinfo=UTC)
    assert last_day <= data_freshness().anchor


def test_equipment_readings_are_anchored() -> None:
    reset_cache()
    body = client.get(
        "/equipment/EQ-003/readings", params={"sensor_type": "temperature", "hours": 24}
    ).json()
    assert body, "锚定数据末尾后读数曲线不应为空"


def test_equipment_detail_reports_data_as_of() -> None:
    reset_cache()
    body = client.get("/equipment/EQ-003").json()
    assert body["data_as_of"] is not None
    assert body["latest_reading_at"] is not None
    assert body["data_lag_hours"] >= 0

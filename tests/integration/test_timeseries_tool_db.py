"""TimeSeries Tool 集成测试：真实时序数据（无库自动跳过）。"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.settings import settings
from tools.timeseries import tool as _tool  # noqa: F401  触发注册

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"
EQUIPMENT_CTX = ToolContext(agent="equipment")


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


def _scenario_a_range(manifest: dict) -> tuple[str, str]:
    scenario = manifest["scenarios"]["equipment_temperature"]
    start = datetime.fromisoformat(scenario["window_start"]) - timedelta(minutes=5)
    end = datetime.fromisoformat(scenario["window_end"])
    return start.isoformat(), end.isoformat()


def test_stats_detects_overheat(manifest: dict) -> None:
    start, end = _scenario_a_range(manifest)
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "sensor",
            "entity_id": "EQ-003",
            "metric": "temperature",
            "op": "stats",
            "start": start,
            "end": end,
        },
        EQUIPMENT_CTX,
    )
    stats = result.data[0]
    assert float(stats["max_value"]) > 88
    assert float(stats["last_value"]) > 88
    assert result.meta["source"] == "postgres:sensor_readings"


def test_series_bucketed(manifest: dict) -> None:
    start, end = _scenario_a_range(manifest)
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "sensor",
            "entity_id": "EQ-003",
            "metric": "temperature",
            "op": "series",
            "bucket": "5m",
            "agg": "avg",
            "start": start,
            "end": end,
        },
        EQUIPMENT_CTX,
    )
    assert result.meta["row_count"] >= 10
    assert all(row["point_count"] >= 1 for row in result.data)


def test_anomaly_windows_finds_ramp(manifest: dict) -> None:
    start, end = _scenario_a_range(manifest)
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "sensor",
            "entity_id": "EQ-003",
            "metric": "temperature",
            "op": "anomaly_windows",
            "threshold": 85,
            "direction": "above",
            "min_duration_minutes": 20,
            "start": start,
            "end": end,
        },
        EQUIPMENT_CTX,
    )
    windows = result.data
    assert len(windows) >= 1
    assert windows[0]["duration_minutes"] >= 20
    assert windows[0]["peak_value"] > 88


def test_process_parameter_series(manifest: dict) -> None:
    import numpy as np

    scenario = manifest["scenarios"]["line_pressure"]
    window_start = datetime.fromisoformat(scenario["window_start"])
    window_end = datetime.fromisoformat(scenario["window_end"])

    def std_for(start: datetime, end: datetime) -> float:
        result = execute_tool(
            "timeseries.query",
            {
                "kind": "process",
                "entity_id": "LINE-2",
                "metric": "pressure",
                "op": "series",
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            ToolContext(agent="process"),
        )
        values = [row["value"] for row in result.data]
        assert len(values) > 30
        return float(np.std(values))

    anomaly_std = std_for(window_start, window_end)
    baseline_std = std_for(window_start - timedelta(days=1), window_end - timedelta(days=1))
    assert anomaly_std > 0.9
    assert baseline_std < 0.6

"""Analysis Tool 集成测试：跨工具协作（TimeSeries/SQL → Analysis）。"""

import json
import os
from datetime import datetime
from pathlib import Path

import psycopg
import pytest

from tools.analysis import tool as _analysis_tool  # noqa: F401  触发注册
from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.settings import settings
from tools.sql import tool as _sql_tool  # noqa: F401  触发注册
from tools.timeseries import tool as _timeseries_tool  # noqa: F401  触发注册

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"


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
            cur.execute("SELECT count(*) FROM quality_inspections")
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


def test_correlation_pressure_vs_valve(manifest: dict) -> None:
    scenario = manifest["scenarios"]["line_pressure"]
    start = datetime.fromisoformat(scenario["window_start"])
    end = datetime.fromisoformat(scenario["window_end"])

    pressure = _series("LINE-2", "pressure", start, end)
    valve = _series("LINE-2", "valve_opening", start, end)
    assert len(pressure) == len(valve) > 30

    data = execute_tool(
        "analysis.run",
        {"op": "correlation", "x": pressure, "y": valve, "method": "pearson"},
        ToolContext(agent="process"),
    ).data
    assert data["r"] > 0.7, "压力应与阀门开度高度相关"


def test_pareto_defect_types() -> None:
    result = execute_tool(
        "sql.query",
        {
            "dataset": "quality_inspections",
            "filters": [{"field": "result", "op": "=", "value": "fail"}],
            "group_by": ["defect_type"],
            "limit": 20,
        },
        ToolContext(agent="quality"),
    )
    labels = [row["defect_type"] for row in result.data]
    counts = [float(row["count"]) for row in result.data]
    assert len(labels) >= 3

    data = execute_tool(
        "analysis.run",
        {"op": "pareto", "labels": labels, "x": counts},
        ToolContext(agent="quality"),
    ).data
    items = data["items"]
    assert items[-1]["cumulative_pct"] == pytest.approx(100.0, abs=0.1)
    top3 = {item["label"] for item in items[:3]}
    assert "surface_crack" in top3


def test_rolling_mean_smooths_sensor(manifest: dict) -> None:
    scenario = manifest["scenarios"]["equipment_temperature"]
    start = datetime.fromisoformat(scenario["window_start"])
    end = datetime.fromisoformat(scenario["window_end"])
    result = execute_tool(
        "timeseries.query",
        {
            "kind": "sensor",
            "entity_id": "EQ-003",
            "metric": "temperature",
            "op": "series",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        ToolContext(agent="equipment"),
    )
    values = [row["value"] for row in result.data]
    data = execute_tool(
        "analysis.run",
        {"op": "rolling_mean", "x": values, "window": 10},
        ToolContext(agent="equipment"),
    ).data
    assert data["last"] > 85, "平滑后末端温度仍应处于高位"

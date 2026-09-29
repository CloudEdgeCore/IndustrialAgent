"""数据层集成测试：需要 PostgreSQL + 已种子数据，否则自动跳过。

运行前置（仓库根目录）：
    docker compose up -d postgres
    alembic -c apps/api/alembic.ini upgrade head
    python -m data.simulator
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from data.simulator.loader import DEFAULT_DATABASE_URL, normalize_database_url

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "manifest.json"


@pytest.fixture(scope="module")
def conn() -> psycopg.Connection:
    url = normalize_database_url(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    try:
        connection = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM sensor_readings")
        if cur.fetchone()[0] == 0:
            connection.close()
            pytest.skip("数据未种子化，先执行 python -m data.simulator")
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def anchor() -> datetime:
    if not MANIFEST_PATH.exists():
        pytest.skip("缺少 manifest.json，先执行 python -m data.simulator")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return datetime.fromisoformat(manifest["anchor"])


def test_extensions_and_hypertables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension")
        names = {row[0] for row in cur.fetchall()}
        assert {"timescaledb", "vector"} <= names

        cur.execute(
            "SELECT hypertable_name FROM timescaledb_information.hypertables "
            "WHERE hypertable_name IN ('sensor_readings', 'process_parameters')"
        )
        hypertables = {row[0] for row in cur.fetchall()}
        assert hypertables == {"sensor_readings", "process_parameters"}


def test_scenario_a_equipment_temperature(
    conn: psycopg.Connection, anchor: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM sensor_readings WHERE equipment_id = 'EQ-003' "
            "AND sensor_type = 'temperature' AND timestamp > %s AND value > 85",
            (anchor - timedelta(minutes=30),),
        )
        assert cur.fetchone()[0] >= 20, "场景 A：近 30 分钟超 85℃ 的点应 ≥20"

        cur.execute(
            "SELECT count(*) FROM alarms WHERE equipment_id = 'EQ-003' "
            "AND alarm_code = 'E102' AND status = 'active'"
        )
        assert cur.fetchone()[0] >= 1, "场景 A：应有活跃的 E102 报警"

        cur.execute(
            "SELECT avg(value) FROM sensor_readings WHERE equipment_id = 'EQ-003' "
            "AND sensor_type = 'flow' AND timestamp > %s",
            (anchor - timedelta(minutes=10),),
        )
        recent_flow = float(cur.fetchone()[0])
        cur.execute(
            "SELECT avg(value) FROM sensor_readings WHERE equipment_id = 'EQ-003' "
            "AND sensor_type = 'flow' AND timestamp BETWEEN %s AND %s",
            (anchor - timedelta(minutes=75), anchor - timedelta(minutes=65)),
        )
        baseline_flow = float(cur.fetchone()[0])
        assert recent_flow < baseline_flow * 0.90, "场景 A：冷却液流量应明显下降"


def test_scenario_b_quality_defect_rate(
    conn: psycopg.Connection, anchor: datetime
) -> None:
    day0 = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_start = day0 - timedelta(days=2)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "  avg((result = 'fail')::int) FILTER (WHERE inspection_time >= %s), "
            "  avg((result = 'fail')::int) FILTER (WHERE inspection_time < %s) "
            "FROM quality_inspections WHERE product_id = 'PRD-A'",
            (recent_start, recent_start),
        )
        recent_rate, baseline_rate = cur.fetchone()
        assert 0.040 <= float(recent_rate) <= 0.052, f"场景 B：近期不良率 {recent_rate}"
        assert 0.015 <= float(baseline_rate) <= 0.021, f"场景 B：基线不良率 {baseline_rate}"

        cur.execute(
            "SELECT count(*) FILTER (WHERE equipment_id = 'EQ-003')::float / count(*) "
            "FROM quality_inspections WHERE product_id = 'PRD-A' AND result = 'fail' "
            "AND inspection_time >= %s",
            (recent_start,),
        )
        assert float(cur.fetchone()[0]) > 0.45, "场景 B：不良应集中于 EQ-003"

        cur.execute(
            "SELECT count(*) FILTER (WHERE defect_type = 'surface_crack')::float / count(*) "
            "FROM quality_inspections WHERE product_id = 'PRD-A' AND result = 'fail' "
            "AND inspection_time >= %s",
            (recent_start,),
        )
        assert float(cur.fetchone()[0]) > 0.40, "场景 B：不良应以表面裂纹为主"


def test_scenario_c_line_pressure_anomaly(
    conn: psycopg.Connection, anchor: datetime
) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    scenario = manifest["scenarios"]["line_pressure"]
    window_start = datetime.fromisoformat(scenario["window_start"])
    window_end = datetime.fromisoformat(scenario["window_end"])

    with conn.cursor() as cur:
        cur.execute(
            "SELECT stddev(value) FROM process_parameters WHERE line_id = 'LINE-2' "
            "AND parameter_name = 'pressure' AND timestamp BETWEEN %s AND %s",
            (window_start, window_end),
        )
        anomaly_std = float(cur.fetchone()[0])
        assert anomaly_std > 0.9, f"场景 C：异常窗口波动应放大（std={anomaly_std}）"

        cur.execute(
            "SELECT stddev(value) FROM process_parameters WHERE line_id = 'LINE-2' "
            "AND parameter_name = 'pressure' AND timestamp BETWEEN %s AND %s",
            (window_start - timedelta(days=1), window_end - timedelta(days=1)),
        )
        baseline_std = float(cur.fetchone()[0])
        assert baseline_std < 0.6, f"场景 C：前一日同时段应平稳（std={baseline_std}）"

        cur.execute(
            "SELECT corr(p.value, v.value) FROM process_parameters p "
            "JOIN process_parameters v ON p.timestamp = v.timestamp "
            "AND p.line_id = v.line_id WHERE p.line_id = 'LINE-2' "
            "AND p.parameter_name = 'pressure' AND v.parameter_name = 'valve_opening' "
            "AND p.timestamp BETWEEN %s AND %s",
            (window_start, window_end),
        )
        corr = float(cur.fetchone()[0])
        assert corr > 0.7, f"场景 C：压力应与阀门开度高度相关（corr={corr}）"


def test_scenario_stopped_equipment(
    conn: psycopg.Connection, anchor: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(timestamp) FROM sensor_readings WHERE equipment_id = 'EQ-024'"
        )
        last_ts = cur.fetchone()[0]
        assert last_ts <= anchor - timedelta(hours=5, minutes=30), "EQ-024 应已停机约 6 小时"

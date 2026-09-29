"""模拟器单元测试：目录一致性、可复现性、场景注入正确性。"""

from datetime import UTC, datetime, timedelta
from itertools import islice

import numpy as np

from data.simulator import generator
from data.simulator.catalog import (
    load_alarm_catalog,
    load_defect_catalog,
    load_equipment,
    load_production,
)

ANCHOR = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def test_equipment_catalog() -> None:
    equipment = load_equipment()
    assert len(equipment) == 30
    assert len({e["equipment_id"] for e in equipment}) == 30
    assert {e["equipment_type"] for e in equipment} == {
        "cnc",
        "injection_molding",
        "assembly_line",
    }
    assert {e["status"] for e in equipment} >= {"alarm", "attention", "stopped"}


def test_alarm_and_defect_catalog() -> None:
    alarms = load_alarm_catalog()
    assert 5 <= len(alarms) <= 10
    assert "E102" in {a["code"] for a in alarms}
    assert all(a["possible_causes"] for a in alarms)

    defects = load_defect_catalog()
    assert 5 <= len(defects) <= 10
    assert "surface_crack" in {d["code"] for d in defects}

    production = load_production()
    assert len(production["lines"]) == 3
    assert len(production["products"]) == 3
    assert {s["shift"] for s in production["shifts"]} == {"day", "night"}


def test_determinism_same_seed() -> None:
    a = list(islice(generator.iter_sensor_rows(42, ANCHOR, 1), 5000))
    b = list(islice(generator.iter_sensor_rows(42, ANCHOR, 1), 5000))
    assert a == b

    assert generator.build_alarms(42, ANCHOR, 10) == generator.build_alarms(42, ANCHOR, 10)
    assert generator.build_batches_and_inspections(
        42, ANCHOR, 5
    ) == generator.build_batches_and_inspections(42, ANCHOR, 5)


def test_sensor_readings_long_table_shape() -> None:
    row = next(iter(generator.iter_sensor_rows(42, ANCHOR, 1)))
    equipment_id, sensor_type, ts, value, quality = row
    assert equipment_id.startswith("EQ-")
    assert sensor_type in {"temperature", "pressure", "speed", "vibration", "current", "flow"}
    assert ts.tzinfo is not None
    assert isinstance(value, float)
    assert quality in {"good", "uncertain"}


def test_scenario_eq003_temperature_ramp() -> None:
    rows = [
        r
        for r in generator.iter_sensor_rows(42, ANCHOR, 2)
        if r[0] == "EQ-003" and r[1] == "temperature"
    ]
    last_30 = [r for r in rows if r[2] > ANCHOR - timedelta(minutes=30)]
    over = [r for r in last_30 if r[3] > generator.SCENARIO_EQ003["threshold"]]
    assert len(over) >= 20, "EQ-003 应连续超过 20 分钟高于 85℃"
    assert rows[-1][3] > 88.0


def test_scenario_eq003_coolant_flow_drop() -> None:
    rows = [
        r
        for r in generator.iter_sensor_rows(42, ANCHOR, 2)
        if r[0] == "EQ-003" and r[1] == "flow"
    ]
    baseline = float(np.mean([r[3] for r in rows[:100]]))
    recent = float(np.mean([r[3] for r in rows[-5:]]))
    assert recent < baseline * 0.90, "冷却液流量应明显下降"


def test_scenario_eq024_stopped() -> None:
    rows = [
        r
        for r in generator.iter_sensor_rows(42, ANCHOR, 2)
        if r[0] == generator.SCENARIO_EQ024["equipment_id"]
    ]
    last_ts = max(r[2] for r in rows)
    assert last_ts <= ANCHOR - timedelta(hours=5, minutes=30)


def test_scenario_line2_pressure_anomaly() -> None:
    rows = [
        r
        for r in generator.iter_process_rows(42, ANCHOR, 3)
        if r[0] == "LINE-2" and r[1] == "pressure"
    ]
    window_start, window_end = generator.line2_window(ANCHOR)
    in_window = [r[3] for r in rows if window_start <= r[2] <= window_end]
    baseline = [
        r[3]
        for r in rows
        if window_start - timedelta(days=1) <= r[2] <= window_end - timedelta(days=1)
    ]
    assert len(in_window) > 30
    assert float(np.std(in_window)) > 0.9, "异常窗口波动应显著放大"
    assert float(np.std(baseline)) < 0.6


def test_scenario_quality_defect_rate() -> None:
    _, inspections = generator.build_batches_and_inspections(42, ANCHOR, 10)
    day0 = ANCHOR.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_start = day0 - timedelta(days=generator.SCENARIO_QUALITY["recent_days"] - 1)

    prd_a = [r for r in inspections if r["product_id"] == "PRD-A"]
    recent = [r for r in prd_a if r["inspection_time"] >= recent_start]
    baseline = [r for r in prd_a if r["inspection_time"] < recent_start]

    recent_rate = sum(r["result"] == "fail" for r in recent) / len(recent)
    baseline_rate = sum(r["result"] == "fail" for r in baseline) / len(baseline)
    assert 0.040 <= recent_rate <= 0.050, f"近期不良率 {recent_rate:.3f} 偏离目标"
    assert 0.015 <= baseline_rate <= 0.021, f"基线不良率 {baseline_rate:.3f} 偏离目标"

    recent_fails = [r for r in recent if r["result"] == "fail"]
    focus_share = sum(
        r["equipment_id"] == generator.SCENARIO_QUALITY["focus_equipment"]
        for r in recent_fails
    ) / len(recent_fails)
    defect_share = sum(
        r["defect_type"] == generator.SCENARIO_QUALITY["focus_defect"]
        for r in recent_fails
    ) / len(recent_fails)
    assert focus_share > 0.45, "近期不良应集中于 EQ-003"
    assert defect_share > 0.40, "近期不良应以表面裂纹为主"


def test_scenario_alarms_and_maintenance() -> None:
    alarms = generator.build_alarms(42, ANCHOR, 60)
    catalog_codes = {a["code"] for a in load_alarm_catalog()}
    assert all(a["alarm_code"] in catalog_codes for a in alarms)
    assert all(a["occurred_at"] <= ANCHOR for a in alarms)

    e102 = [
        a
        for a in alarms
        if a["equipment_id"] == "EQ-003" and a["alarm_code"] == "E102" and a["status"] == "active"
    ]
    assert len(e102) == 1

    maintenance = generator.build_maintenance(42, ANCHOR, 60, alarms)
    assert any(
        m["equipment_id"] == "EQ-003" and m["root_cause"] == "冷却过滤器堵塞"
        for m in maintenance
    )

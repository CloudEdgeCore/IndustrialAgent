"""工业数据模拟器：固定随机种子生成可复现的演示数据（含场景注入）。

场景（与 PRD §4 场景 A/B/C 对齐）：
- A 设备故障诊断：EQ-003 主轴温度末段爬升（连续 >20 分钟超过 85℃），
  伴随 E102 报警与冷却液流量下降 18%；
- B 质量问题溯源：PRD-A 最近 3 天不良率约 1.8% → 4.6%，集中
  在 EQ-003 / surface_crack；
- C 工艺异常分析：LINE-2 压力昨日 15:20-16:05（Asia/Shanghai）波动异常，
  与阀门开度（valve_opening）变化高度相关；
- 附带：EQ-017 振动爬升（attention）、EQ-024 停机（stopped）。

所有随机过程使用 numpy 固定种子生成器，同 seed + 同 anchor 完全可复现。
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from data.simulator.catalog import (
    load_alarm_catalog,
    load_defect_catalog,
    load_equipment,
    load_production,
)

CST = ZoneInfo("Asia/Shanghai")
UTC = UTC

SENSOR_BASELINES: dict[str, dict[str, tuple[float, float]]] = {
    "cnc": {
        "temperature": (58.0, 3.0),
        "pressure": (4.5, 0.15),
        "speed": (8200.0, 150.0),
        "vibration": (2.8, 0.6),
        "current": (42.0, 2.5),
        "flow": (18.0, 0.8),
    },
    "injection_molding": {
        "temperature": (182.0, 4.0),
        "pressure": (88.0, 3.0),
        "speed": (125.0, 6.0),
        "vibration": (3.4, 0.8),
        "current": (65.0, 4.0),
    },
    "assembly_line": {
        "temperature": (42.0, 2.5),
        "pressure": (6.2, 0.2),
        "speed": (14.5, 0.5),
        "vibration": (1.9, 0.4),
        "current": (18.0, 1.5),
    },
}

PROCESS_BASELINES: dict[str, dict[str, tuple[float, float]]] = {
    "LINE-1": {
        "temperature": (60.0, 2.0),
        "pressure": (6.5, 0.3),
        "speed": (7800.0, 120.0),
        "flow": (20.0, 0.9),
        "valve_opening": (40.0, 1.5),
    },
    "LINE-2": {
        "temperature": (64.0, 2.2),
        "pressure": (8.2, 0.35),
        "speed": (7600.0, 130.0),
        "flow": (19.0, 1.0),
        "valve_opening": (44.0, 1.6),
    },
    "LINE-3": {
        "temperature": (70.0, 2.5),
        "pressure": (7.4, 0.3),
        "speed": (6900.0, 140.0),
        "flow": (17.0, 1.1),
        "valve_opening": (46.0, 1.8),
    },
}

# ---- 场景参数（测试与 manifest 共用，勿随意改动） ----

SCENARIO_EQ003 = {
    "equipment_id": "EQ-003",
    "sensor_type": "temperature",
    "ramp_minutes": 60,
    "ramp_start": 76.0,
    "ramp_end": 91.0,
    "threshold": 85.0,
    "flow_drop_pct": 0.18,
    "alarm_code": "E102",
    "alarm_lead_minutes": 40,
}

SCENARIO_EQ017 = {
    "equipment_id": "EQ-017",
    "sensor_type": "vibration",
    "ramp_minutes": 120,
    "ramp_end": 5.6,
    "alarm_code": "E501",
}

SCENARIO_EQ024 = {
    "equipment_id": "EQ-024",
    "stop_hours": 6,
    "alarm_code": "E301",
}

SCENARIO_LINE2 = {
    "line_id": "LINE-2",
    "parameter_name": "pressure",
    "local_start": (15, 20),
    "local_end": (16, 5),
    "amplitude": 1.6,
    "mean_shift": 0.8,
    "period_minutes": 3.0,
    "valve_amplitude": 8.0,
}

SCENARIO_QUALITY = {
    "product_id": "PRD-A",
    "recent_days": 3,
    "baseline_rate": 0.018,
    "focus_equipment": "EQ-003",
    "focus_equipment_rate": 0.15,
    "other_recent_rate": 0.023,
    "night_extra_rate": 0.004,
    "focus_defect": "surface_crack",
    "focus_defect_share": 0.70,
    "process_temp_offset": 7.0,
}

BASE_DEFECT_WEIGHTS = {
    "surface_crack": 0.20,
    "dimension_deviation": 0.20,
    "burr": 0.18,
    "porosity": 0.12,
    "scratch": 0.15,
    "color_deviation": 0.15,
}

FOCUS_DEFECT_WEIGHTS = {
    "surface_crack": 0.70,
    "dimension_deviation": 0.08,
    "burr": 0.07,
    "porosity": 0.05,
    "scratch": 0.05,
    "color_deviation": 0.05,
}

TECHNICIANS = ["张工", "李工", "王工", "刘工", "陈工"]


def resolve_anchor(anchor: datetime | None) -> datetime:
    """归一化锚点时间：默认当前 UTC，截断到分钟。"""
    if anchor is None:
        anchor = datetime.now(UTC)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    return anchor.astimezone(UTC).replace(second=0, microsecond=0)


def line2_window(anchor: datetime) -> tuple[datetime, datetime]:
    """LINE-2 压力异常窗口：昨日 15:20-16:05（Asia/Shanghai）→ UTC。"""
    local = anchor.astimezone(CST)
    hour, minute = SCENARIO_LINE2["local_start"]
    start = local.replace(hour=hour, minute=minute) - timedelta(days=1)
    hour, minute = SCENARIO_LINE2["local_end"]
    end = local.replace(hour=hour, minute=minute) - timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def _minute_axis(anchor: datetime, days: int) -> np.ndarray:
    n = days * 1440 + 1
    base = np.datetime64(anchor.replace(tzinfo=None), "m")
    return base - np.arange(n)[::-1] * np.timedelta64(1, "m")


def _series(
    rng: np.random.Generator, mean: float, sigma: float, n: int
) -> np.ndarray:
    t = np.arange(n)
    seasonal = mean * 0.02 * np.sin(2 * np.pi * t / 1440.0)
    return mean + seasonal + rng.normal(0.0, sigma, n)


def _quality_flags(rng: np.random.Generator, n: int) -> np.ndarray:
    return np.where(rng.random(n) < 0.002, "uncertain", "good")


def iter_sensor_rows(
    seed: int, anchor: datetime, days: int
) -> Iterator[tuple[str, str, datetime, float, str]]:
    """产出 sensor_readings 行（长表）：(equipment_id, sensor_type, timestamp, value, quality)。"""
    rng = np.random.default_rng(seed + 1)
    ts = _minute_axis(anchor, days)
    n = len(ts)
    stop_time = np.datetime64(
        (anchor - timedelta(hours=SCENARIO_EQ024["stop_hours"])).replace(tzinfo=None), "m"
    )

    for eq in load_equipment():
        eq_id = eq["equipment_id"]
        baselines = SENSOR_BASELINES[eq["equipment_type"]]
        for sensor_type, (mean, sigma) in baselines.items():
            values = _series(rng, mean, sigma, n)

            if eq_id == SCENARIO_EQ003["equipment_id"]:
                k = SCENARIO_EQ003["ramp_minutes"]
                if sensor_type == "temperature":
                    ramp = np.linspace(
                        SCENARIO_EQ003["ramp_start"], SCENARIO_EQ003["ramp_end"], k
                    )
                    values[-k:] = ramp + rng.normal(0.0, sigma * 0.4, k)
                elif sensor_type == "flow":
                    decay = 1.0 - SCENARIO_EQ003["flow_drop_pct"] * np.linspace(0, 1, k)
                    values[-k:] = values[-k:] * decay
                elif sensor_type == "vibration":
                    values[-k:] = np.linspace(mean, 4.5, k) + rng.normal(0.0, sigma * 0.5, k)

            if eq_id == SCENARIO_EQ017["equipment_id"] and sensor_type == "vibration":
                k = SCENARIO_EQ017["ramp_minutes"]
                values[-k:] = np.linspace(mean, SCENARIO_EQ017["ramp_end"], k) + rng.normal(
                    0.0, sigma * 0.5, k
                )

            qualities = _quality_flags(rng, n)
            keep = np.ones(n, dtype=bool)
            if eq_id == SCENARIO_EQ024["equipment_id"]:
                keep = ts <= stop_time

            for i in np.where(keep)[0]:
                yield (
                    eq_id,
                    sensor_type,
                    ts[i].item().replace(tzinfo=UTC),
                    round(float(values[i]), 3),
                    str(qualities[i]),
                )


def iter_process_rows(
    seed: int, anchor: datetime, days: int
) -> Iterator[tuple[str, str, datetime, float, str]]:
    """产出 process_parameters 行：(line_id, parameter_name, timestamp, value, quality)。"""
    rng = np.random.default_rng(seed + 2)
    ts = _minute_axis(anchor, days)
    n = len(ts)
    window_start, window_end = line2_window(anchor)
    ws = np.datetime64(window_start.replace(tzinfo=None), "m")
    we = np.datetime64(window_end.replace(tzinfo=None), "m")
    t = np.arange(n)

    for line_id, baselines in PROCESS_BASELINES.items():
        for parameter, (mean, sigma) in baselines.items():
            values = _series(rng, mean, sigma, n)

            if line_id == SCENARIO_LINE2["line_id"]:
                mask = (ts >= ws) & (ts <= we)
                if mask.any():
                    phase = (
                        2
                        * np.pi
                        * (t[mask] - t[mask][0])
                        / SCENARIO_LINE2["period_minutes"]
                    )
                    if parameter == SCENARIO_LINE2["parameter_name"]:
                        values[mask] += SCENARIO_LINE2["mean_shift"]
                        values[mask] += SCENARIO_LINE2["amplitude"] * np.sin(phase)
                    elif parameter == "valve_opening":
                        values[mask] += SCENARIO_LINE2["valve_amplitude"] * np.sin(phase)
                    elif parameter == "flow":
                        values[mask] += 0.8 * np.sin(phase + np.pi / 2)

            qualities = _quality_flags(rng, n)
            for i in range(n):
                yield (
                    line_id,
                    parameter,
                    ts[i].item().replace(tzinfo=UTC),
                    round(float(values[i]), 3),
                    str(qualities[i]),
                )


def build_equipment() -> list[dict]:
    return load_equipment()


def build_alarms(seed: int, anchor: datetime, history_days: int) -> list[dict]:
    rng = np.random.default_rng(seed + 3)
    catalog = load_alarm_catalog()
    by_code = {item["code"]: item for item in catalog}
    codes = [item["code"] for item in catalog]
    weights = np.array(
        [{"critical": 0.3, "warning": 0.55, "info": 0.15}[item["severity"]] for item in catalog]
    )
    weights = weights / weights.sum()

    rows: list[dict] = []
    for eq in load_equipment():
        eq_id = eq["equipment_id"]
        for d in range(history_days):
            if rng.random() >= 0.06:
                continue
            occurred = anchor - timedelta(days=d, minutes=int(rng.integers(0, 1440)))
            code = str(rng.choice(codes, p=weights))
            severity = by_code[code]["severity"]
            draw = rng.random()
            if draw < 0.80:
                status = "cleared"
                cleared_at = occurred + timedelta(minutes=int(rng.integers(30, 480)))
            elif draw < 0.95:
                status = "acknowledged"
                cleared_at = None
            else:
                status = "active"
                cleared_at = None
            rows.append(
                {
                    "alarm_code": code,
                    "equipment_id": eq_id,
                    "severity": severity,
                    "status": status,
                    "occurred_at": occurred,
                    "cleared_at": cleared_at,
                    "description": by_code[code]["description"],
                }
            )

    def scenario_alarm(eq_id: str, code: str, occurred: datetime, status: str) -> dict:
        return {
            "alarm_code": code,
            "equipment_id": eq_id,
            "severity": by_code[code]["severity"],
            "status": status,
            "occurred_at": occurred,
            "cleared_at": None,
            "description": by_code[code]["description"],
        }

    rows.append(
        scenario_alarm(
            SCENARIO_EQ003["equipment_id"],
            SCENARIO_EQ003["alarm_code"],
            anchor - timedelta(minutes=SCENARIO_EQ003["alarm_lead_minutes"]),
            "active",
        )
    )
    rows.append(
        scenario_alarm(
            SCENARIO_EQ017["equipment_id"],
            SCENARIO_EQ017["alarm_code"],
            anchor - timedelta(minutes=90),
            "acknowledged",
        )
    )
    rows.append(
        scenario_alarm(
            SCENARIO_EQ024["equipment_id"],
            SCENARIO_EQ024["alarm_code"],
            anchor - timedelta(hours=SCENARIO_EQ024["stop_hours"]),
            "active",
        )
    )
    return rows


def build_maintenance(
    seed: int, anchor: datetime, history_days: int, alarms: list[dict]
) -> list[dict]:
    rng = np.random.default_rng(seed + 4)
    catalog = load_alarm_catalog()
    causes_by_code = {item["code"]: item["possible_causes"] for item in catalog}

    rows: list[dict] = []
    for alarm in alarms:
        if alarm["status"] == "active" or rng.random() >= 0.30:
            continue
        occurred = alarm["occurred_at"] + timedelta(hours=float(rng.uniform(1, 10)))
        cause = str(rng.choice(causes_by_code.get(alarm["alarm_code"], ["待分析"])))
        rows.append(
            {
                "equipment_id": alarm["equipment_id"],
                "maintenance_type": "corrective",
                "description": f"{alarm['equipment_id']} {alarm['alarm_code']} 报警检修",
                "root_cause": cause,
                "actions": f"针对 {alarm['alarm_code']} 完成检修：{cause}，已恢复生产",
                "technician": str(rng.choice(TECHNICIANS)),
                "related_alarm_code": alarm["alarm_code"],
                "occurred_at": occurred,
                "completed_at": occurred + timedelta(hours=float(rng.uniform(1, 4))),
            }
        )

    for eq in load_equipment():
        if rng.random() >= 0.5:
            continue
        occurred = anchor - timedelta(
            days=int(rng.integers(5, history_days)), minutes=int(rng.integers(0, 1440))
        )
        rows.append(
            {
                "equipment_id": eq["equipment_id"],
                "maintenance_type": "preventive",
                "description": f"{eq['name']} 定期保养",
                "root_cause": None,
                "actions": "按保养计划完成润滑、紧固、清洁与参数校验",
                "technician": str(rng.choice(TECHNICIANS)),
                "related_alarm_code": None,
                "occurred_at": occurred,
                "completed_at": occurred + timedelta(hours=float(rng.uniform(2, 6))),
            }
        )

    rows.append(
        {
            "equipment_id": "EQ-003",
            "maintenance_type": "corrective",
            "description": "3 号数控加工中心冷却系统检修",
            "root_cause": "冷却过滤器堵塞",
            "actions": "更换冷却液过滤器并补充冷却液，主轴温度恢复正常",
            "technician": "王工",
            "related_alarm_code": "E102",
            "occurred_at": anchor - timedelta(days=73),
            "completed_at": anchor - timedelta(days=73) + timedelta(hours=3),
        }
    )
    return rows


def build_batches_and_inspections(
    seed: int, anchor: datetime, quality_days: int
) -> tuple[list[dict], list[dict]]:
    rng = np.random.default_rng(seed + 5)
    production = load_production()
    products = production["products"]
    equipment = load_equipment()
    pool_by_line_type: dict[tuple[str, str], list[str]] = {}
    for eq in equipment:
        key = (eq["production_line"], eq["equipment_type"])
        pool_by_line_type.setdefault(key, []).append(eq["equipment_id"])

    defect_codes = list(BASE_DEFECT_WEIGHTS.keys())
    base_weights = np.array([BASE_DEFECT_WEIGHTS[c] for c in defect_codes])
    focus_weights = np.array([FOCUS_DEFECT_WEIGHTS[c] for c in defect_codes])

    day0 = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    batches: list[dict] = []
    inspections: list[dict] = []
    fail_residual: dict[tuple[str, str], float] = {}
    pool_counters: dict[tuple[str, str], int] = {}

    for d in range(quality_days):
        day_start = day0 - timedelta(days=d)
        recent = d < SCENARIO_QUALITY["recent_days"]
        seq = 0
        for product in products:
            product_id = product["product_id"]
            pool = pool_by_line_type[(product["production_line"], product["equipment_type"])]
            baselines = SENSOR_BASELINES[product["equipment_type"]]
            for shift, shift_offset_hours in (("day", 0), ("night", 12)):
                for _ in range(6):
                    # 设备轮转分配：保证各设备批次份额均衡（不良率口径稳定）
                    pool_key = (product["production_line"], product["equipment_type"])
                    counter = pool_counters.get(pool_key, 0)
                    eq_id = pool[counter % len(pool)]
                    pool_counters[pool_key] = counter + 1
                    started = day_start + timedelta(
                        hours=shift_offset_hours, minutes=int(rng.integers(0, 600))
                    )
                    if started > anchor:
                        continue
                    seq += 1
                    units = int(rng.integers(50, 71))

                    if product_id == SCENARIO_QUALITY["product_id"] and recent:
                        if eq_id == SCENARIO_QUALITY["focus_equipment"]:
                            rate = SCENARIO_QUALITY["focus_equipment_rate"]
                        else:
                            rate = SCENARIO_QUALITY["other_recent_rate"]
                        if shift == "night":
                            rate += SCENARIO_QUALITY["night_extra_rate"]
                    else:
                        rate = SCENARIO_QUALITY["baseline_rate"]

                    # 余数进位：保证批次级舍入不损失整体不良率（收敛到目标值）
                    key = (product_id, "recent" if recent else "baseline")
                    residual = fail_residual.get(key, 0.0) + rate * units
                    n_fail = int(residual)
                    fail_residual[key] = residual - n_fail
                    fails = np.zeros(units, dtype=bool)
                    if n_fail > 0:
                        fails[rng.choice(units, size=n_fail, replace=False)] = True
                    batch_id = f"B{started:%Y%m%d}{seq:03d}"
                    batches.append(
                        {
                            "batch_id": batch_id,
                            "product_id": product_id,
                            "equipment_id": eq_id,
                            "production_line": product["production_line"],
                            "shift": shift,
                            "started_at": started,
                            "finished_at": started + timedelta(hours=3),
                            "quantity": units,
                        }
                    )

                    for i in range(units):
                        t_insp = started + timedelta(minutes=int(rng.integers(30, 300)))
                        if t_insp > anchor:
                            t_insp = anchor
                        result = "fail" if fails[i] else "pass"
                        defect_type = None
                        if result == "fail":
                            focused = (
                                product_id == SCENARIO_QUALITY["product_id"]
                                and recent
                                and eq_id == SCENARIO_QUALITY["focus_equipment"]
                            )
                            weights = focus_weights if focused else base_weights
                            defect_type = str(rng.choice(defect_codes, p=weights))
                        temp_mean, temp_sigma = baselines["temperature"]
                        press_mean, press_sigma = baselines["pressure"]
                        temp = float(rng.normal(temp_mean, temp_sigma))
                        press = float(rng.normal(press_mean, press_sigma))
                        if (
                            defect_type == SCENARIO_QUALITY["focus_defect"]
                            and eq_id == SCENARIO_QUALITY["focus_equipment"]
                            and recent
                        ):
                            temp += SCENARIO_QUALITY["process_temp_offset"]
                        inspections.append(
                            {
                                "batch_id": batch_id,
                                "product_id": product_id,
                                "equipment_id": eq_id,
                                "shift": shift,
                                "inspection_time": t_insp,
                                "result": result,
                                "defect_type": defect_type,
                                "process_temperature": round(temp, 3),
                                "process_pressure": round(press, 3),
                            }
                        )

    return batches, inspections


def build_manifest(
    seed: int,
    anchor: datetime,
    days: int,
    quality_days: int,
    history_days: int,
    counts: dict[str, int] | None = None,
) -> dict:
    window_start, window_end = line2_window(anchor)
    return {
        "seed": seed,
        "anchor": anchor.isoformat(),
        "days": days,
        "quality_days": quality_days,
        "history_days": history_days,
        "counts": counts or {},
        "scenarios": {
            "equipment_temperature": {
                "equipment_id": SCENARIO_EQ003["equipment_id"],
                "sensor_type": SCENARIO_EQ003["sensor_type"],
                "threshold": SCENARIO_EQ003["threshold"],
                "window_start": (
                    anchor - timedelta(minutes=SCENARIO_EQ003["ramp_minutes"])
                ).isoformat(),
                "window_end": anchor.isoformat(),
                "alarm_code": SCENARIO_EQ003["alarm_code"],
            },
            "equipment_stopped": {
                "equipment_id": SCENARIO_EQ024["equipment_id"],
                "stopped_at": (
                    anchor - timedelta(hours=SCENARIO_EQ024["stop_hours"])
                ).isoformat(),
            },
            "line_pressure": {
                "line_id": SCENARIO_LINE2["line_id"],
                "parameter_name": SCENARIO_LINE2["parameter_name"],
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
            },
            "quality_defect_rate": {
                "product_id": SCENARIO_QUALITY["product_id"],
                "recent_days": SCENARIO_QUALITY["recent_days"],
                "baseline_rate": SCENARIO_QUALITY["baseline_rate"],
                "focus_equipment": SCENARIO_QUALITY["focus_equipment"],
                "focus_defect": SCENARIO_QUALITY["focus_defect"],
            },
        },
    }


def iter_defect_rows() -> Iterator[dict]:
    for item in load_defect_catalog():
        yield {
            "defect_code": item["code"],
            "name": item["name"],
            "category": item.get("category"),
            "description": item.get("description"),
        }

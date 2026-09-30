"""TimeSeries Tool：设备传感器 / 产线工艺参数时序查询。

能力（架构 §8）：最近 N 分钟、时间窗口聚合、最大/最小/均值、异常时间段。
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from tools.timeutils import parse_relative

SENSOR_TYPES = ("temperature", "pressure", "speed", "vibration", "current", "flow")
PROCESS_PARAMETERS = ("temperature", "pressure", "speed", "flow", "valve_opening")

_METRIC_ALIASES = {
    "coolant_flow": "flow",
    "coolant": "flow",
    "flow_rate": "flow",
    "冷却液流量": "flow",
    "spindle_speed": "speed",
    "rpm": "speed",
    "rotation_speed": "speed",
    "主轴转速": "speed",
    "spindle_temp": "temperature",
    "spindle_temperature": "temperature",
    "temp": "temperature",
    "temperature_c": "temperature",
    "vibration_rms": "vibration",
    "vibration_value": "vibration",
    "press": "pressure",
    "valve": "valve_opening",
    "valve_position": "valve_opening",
    "valve_opening_ratio": "valve_opening",
}

_ENTITY_RE = re.compile(r"^(EQ|LINE)[-_ ]?0*(\d+)$", re.IGNORECASE)

BUCKETS = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "1d": "1 day",
}

BUCKET_AGGS = {"avg": "avg", "min": "min", "max": "max", "stddev": "stddev", "count": "count"}

MAX_RAW_LIMIT = 5000

_EQ_RE = re.compile(r"^EQ-\d{3}$")
_LINE_RE = re.compile(r"^LINE-\d$")


class TimeSeriesParams(BaseModel):
    kind: Literal["sensor", "process"] = Field(
        description="sensor=设备传感器读数；process=产线工艺参数"
    )
    entity_id: str = Field(description="设备编号（EQ-xxx）或产线编号（LINE-x）")
    metric: str = Field(description="指标名，如 temperature / pressure / valve_opening")
    op: Literal["series", "stats", "anomaly_windows"] = "series"
    relative: str | None = Field(
        default=None,
        description="相对时间：last_1h / last_24h / last_3d / last_7d / last_30d / "
        "last_Nm / last_Nh / last_Nd / today / yesterday，默认 last_24h",
    )
    start: datetime | None = None
    end: datetime | None = None
    bucket: Literal["1m", "5m", "15m", "1h", "1d"] | None = Field(
        default=None, description="series 聚合粒度；不设则返回原始点"
    )
    agg: Literal["avg", "min", "max", "stddev", "count"] = "avg"
    threshold: float | None = Field(default=None, description="anomaly_windows 阈值")
    direction: Literal["above", "below"] = "above"
    min_duration_minutes: int = Field(default=1, ge=1, le=1440)
    limit: int = Field(default=2000, ge=1, le=MAX_RAW_LIMIT)

    @field_validator("metric", mode="before")
    @classmethod
    def _normalize_metric(cls, value: object) -> object:
        if isinstance(value, str):
            key = value.strip().lower().replace(" ", "_")
            return _METRIC_ALIASES.get(key, key)
        return value

    @field_validator("entity_id", mode="before")
    @classmethod
    def _normalize_entity(cls, value: object) -> object:
        if isinstance(value, str):
            match = _ENTITY_RE.match(value.strip())
            if match:
                prefix, number = match.groups()
                prefix = prefix.upper()
                if prefix == "EQ":
                    return f"EQ-{int(number):03d}"
                return f"LINE-{int(number)}"
        return value

    @model_validator(mode="after")
    def _validate(self) -> "TimeSeriesParams":
        if self.kind == "sensor":
            if not _EQ_RE.match(self.entity_id):
                raise ValueError(f"非法设备编号: {self.entity_id}（应形如 EQ-003）")
            if self.metric not in SENSOR_TYPES:
                raise ValueError(
                    f"非法传感器指标: {self.metric}（可用: {list(SENSOR_TYPES)}）"
                )
        else:
            if not _LINE_RE.match(self.entity_id):
                raise ValueError(f"非法产线编号: {self.entity_id}（应形如 LINE-2）")
            if self.metric not in PROCESS_PARAMETERS:
                raise ValueError(
                    f"非法工艺参数: {self.metric}（可用: {list(PROCESS_PARAMETERS)}）"
                )
        if self.relative is not None and parse_relative(self.relative) is None:
            raise ValueError(
                f"非法相对时间: {self.relative}"
                "（支持 last_1h/last_24h/last_Nm/last_Nh/last_Nd/today/yesterday）"
            )
        if self.op == "anomaly_windows" and self.threshold is None:
            raise ValueError("anomaly_windows 需要 threshold")
        if self.bucket is not None and self.bucket not in BUCKETS:
            raise ValueError(f"非法聚合粒度: {self.bucket}")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start 必须早于 end")
        return self

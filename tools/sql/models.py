"""结构化查询模型（禁止 LLM 生成任意 SQL，只允许产出此结构的查询）。

容错层：真实 LLM 常把嵌套对象/列表序列化为 JSON 字符串，
或使用近义算子/函数名（contains/mean/…），此处统一在验证前归一化。
"""

import ast
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FilterOp = Literal["=", "!=", ">", ">=", "<", "<=", "in", "like", "is_null"]
MetricFunc = Literal["count", "avg", "min", "max", "sum", "stddev"]

_OP_ALIASES = {
    "eq": "=",
    "==": "=",
    "is": "=",
    "neq": "!=",
    "ne": "!=",
    "<>": "!=",
    "gte": ">=",
    "ge": ">=",
    "lte": "<=",
    "le": "<=",
    "gt": ">",
    "lt": "<",
    "contains": "like",
    "has": "like",
    "match": "like",
    "isnull": "is_null",
    "not_null": "is_null",
}

_FUNC_ALIASES = {
    "mean": "avg",
    "average": "avg",
    "std": "stddev",
    "std_dev": "stddev",
    "stddev_pop": "stddev",
    "total": "sum",
}


def coerce_json_value(value: Any) -> Any:
    """字符串形式的 JSON/字面量 → Python 对象（解析失败原样返回）。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except Exception:  # noqa: BLE001 - 解析失败则原样返回
            continue
    return value


def _coerce_field(value: Any) -> Any:
    return coerce_json_value(value).strip().lower() if isinstance(
        coerce_json_value(value), str
    ) else coerce_json_value(value)


class Filter(BaseModel):
    field: str = Field(description="字段名（必须在数据集白名单内）")
    op: FilterOp
    value: Any | None = None

    @field_validator("field", mode="before")
    @classmethod
    def _normalize_field(cls, value: Any) -> Any:
        coerced = coerce_json_value(value)
        return coerced.strip().lower() if isinstance(coerced, str) else coerced

    @field_validator("op", mode="before")
    @classmethod
    def _normalize_op(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().lower()
            return _OP_ALIASES.get(key, key)
        return value

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, value: Any) -> Any:
        return coerce_json_value(value)


class Metric(BaseModel):
    func: MetricFunc
    field: str = Field(default="*", description="count 可用 *，其余需数值字段")
    alias: str | None = None

    @field_validator("func", mode="before")
    @classmethod
    def _normalize_func(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().lower()
            return _FUNC_ALIASES.get(key, key)
        return value

    @field_validator("field", mode="before")
    @classmethod
    def _normalize_field(cls, value: Any) -> Any:
        coerced = coerce_json_value(value)
        return coerced.strip().lower() if isinstance(coerced, str) else coerced


class OrderBy(BaseModel):
    field: str
    desc: bool = True

    @field_validator("field", mode="before")
    @classmethod
    def _normalize_field(cls, value: Any) -> Any:
        coerced = coerce_json_value(value)
        return coerced.strip().lower() if isinstance(coerced, str) else coerced


class TimeRange(BaseModel):
    field: str | None = Field(default=None, description="默认数据集时间字段")
    relative: str | None = Field(
        default=None,
        description="相对时间：last_1h/last_24h/last_3d/last_7d/last_30d/"
        "last_Nm/last_Nh/last_Nd/today/yesterday",
    )
    start: datetime | None = None
    end: datetime | None = None


class StructuredQuery(BaseModel):
    dataset: str = Field(
        description="数据集：equipment/alarms/maintenance_records/"
        "product_batches/quality_inspections/defects"
    )
    select: list[str] | None = Field(default=None, description="返回列；默认全部")
    filters: list[Filter] = Field(default_factory=list)
    time_range: TimeRange | None = None
    group_by: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int = Field(default=100, description="最大 1000")

    @field_validator("dataset", mode="before")
    @classmethod
    def _normalize_dataset(cls, value: Any) -> Any:
        coerced = coerce_json_value(value)
        return coerced.strip().lower() if isinstance(coerced, str) else coerced

    @field_validator("select", "group_by", mode="before")
    @classmethod
    def _normalize_str_list(cls, value: Any) -> Any:
        coerced = coerce_json_value(value)
        if coerced is None:
            return None
        if isinstance(coerced, str):
            return [part.strip().lower() for part in coerced.split(",") if part.strip()]
        if isinstance(coerced, (list, tuple)):
            return [
                item.strip().lower() if isinstance(item, str) else item
                for item in coerced
            ]
        return coerced

    @field_validator("filters", "metrics", "order_by", mode="before")
    @classmethod
    def _normalize_obj_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return coerce_json_value(value)

    @field_validator("time_range", mode="before")
    @classmethod
    def _normalize_time_range(cls, value: Any) -> Any:
        if value is None:
            return None
        return coerce_json_value(value)

"""结构化查询模型（禁止 LLM 生成任意 SQL，只允许产出此结构的查询）。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

FilterOp = Literal["=", "!=", ">", ">=", "<", "<=", "in", "like", "is_null"]
MetricFunc = Literal["count", "avg", "min", "max", "sum", "stddev"]
RelativeRange = Literal[
    "last_1h", "last_24h", "last_3d", "last_7d", "last_30d", "today", "yesterday"
]


class Filter(BaseModel):
    field: str = Field(description="字段名（必须在数据集白名单内）")
    op: FilterOp
    value: Any | None = None


class Metric(BaseModel):
    func: MetricFunc
    field: str = Field(default="*", description="count 可用 *，其余需数值字段")
    alias: str | None = None


class OrderBy(BaseModel):
    field: str
    desc: bool = True


class TimeRange(BaseModel):
    field: str | None = Field(default=None, description="默认数据集时间字段")
    relative: RelativeRange | None = None
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

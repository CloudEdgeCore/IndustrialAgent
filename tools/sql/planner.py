"""Query Planner：结构化查询 → 白名单校验与归一化。

架构 §7 流程：Natural Language → Query Planner → Structured Query → SQL Builder
→ SQL Validator → Read-only DB（LLM 永不接触原始 SQL）。
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from tools.base import ToolValidationError
from tools.sql.models import Filter, Metric, OrderBy, StructuredQuery, TimeRange
from tools.sql.schema import DATASETS, DatasetSpec

MAX_LIMIT = 1000
_ALIAS_RE = re.compile(r"^[a-z_][a-z0-9_]{0,31}$")


@dataclass
class PlannedQuery:
    spec: DatasetSpec
    select: list[str]
    filters: list[Filter]
    group_by: list[str]
    metrics: list[Metric]
    order_by: list[OrderBy]
    limit: int


def _relative_window(relative: str, now: datetime) -> tuple[datetime, datetime]:
    if relative == "last_1h":
        return now - timedelta(hours=1), now
    if relative == "last_24h":
        return now - timedelta(hours=24), now
    if relative == "last_3d":
        return now - timedelta(days=3), now
    if relative == "last_7d":
        return now - timedelta(days=7), now
    if relative == "last_30d":
        return now - timedelta(days=30), now
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if relative == "today":
        return day0, now
    if relative == "yesterday":
        return day0 - timedelta(days=1), day0
    raise ToolValidationError(f"未知时间范围: {relative}")


def _validate_metric(metric: Metric, spec: DatasetSpec) -> None:
    if metric.func == "count":
        if metric.field != "*" and metric.field not in spec.columns:
            raise ToolValidationError(f"count 字段不在白名单: {metric.field}")
    else:
        if metric.field not in spec.numeric_columns:
            raise ToolValidationError(
                f"聚合字段必须是数值列: {metric.field}（可用: {spec.numeric_columns}）"
            )
    if metric.alias and not _ALIAS_RE.match(metric.alias):
        raise ToolValidationError(f"非法别名: {metric.alias}")


def plan(query: StructuredQuery) -> PlannedQuery:
    spec = DATASETS.get(query.dataset)
    if spec is None:
        raise ToolValidationError(
            f"未知数据集: {query.dataset}（白名单: {sorted(DATASETS)}）"
        )
    columns = set(spec.columns)

    if not query.select or query.select == ["*"]:
        select = list(spec.columns)
    else:
        for column in query.select:
            if column not in columns:
                raise ToolValidationError(f"字段不在白名单: {column}")
        select = list(query.select)

    metrics: list[Metric] = []
    for metric in query.metrics:
        _validate_metric(metric, spec)
        metrics.append(metric)

    for group in query.group_by:
        if group not in columns:
            raise ToolValidationError(f"分组字段不在白名单: {group}")

    if query.group_by and not metrics:
        metrics.append(Metric(func="count", field="*", alias="count"))

    filters: list[Filter] = []
    for flt in query.filters:
        if flt.field not in columns:
            raise ToolValidationError(f"过滤字段不在白名单: {flt.field}")
        if flt.op == "in" and (not isinstance(flt.value, list) or not flt.value):
            raise ToolValidationError("in 操作需要非空列表")
        if flt.op == "like" and not isinstance(flt.value, str):
            raise ToolValidationError("like 操作需要字符串")
        if flt.op == "is_null" and not isinstance(flt.value, bool):
            raise ToolValidationError("is_null 操作需要布尔值")
        filters.append(flt)

    if query.time_range is not None:
        filters.extend(_time_filters(query.time_range, spec))

    aliases = {m.alias for m in metrics if m.alias}
    order_by: list[OrderBy] = []
    for order in query.order_by:
        if order.field not in columns and order.field not in aliases:
            raise ToolValidationError(f"排序字段不在白名单: {order.field}")
        order_by.append(order)
    if not order_by:
        if metrics:
            first_alias = metrics[0].alias or metrics[0].func
            order_by = [OrderBy(field=first_alias, desc=True)]
        else:
            order_by = [
                OrderBy(field=spec.default_order_field, desc=spec.default_order_desc)
            ]

    limit = max(1, min(query.limit, MAX_LIMIT))
    return PlannedQuery(
        spec=spec,
        select=select,
        filters=filters,
        group_by=list(query.group_by),
        metrics=metrics,
        order_by=order_by,
        limit=limit,
    )


def _time_filters(time_range: TimeRange, spec: DatasetSpec) -> list[Filter]:
    field = time_range.field or spec.time_field
    if field not in spec.columns:
        raise ToolValidationError(f"时间字段不在白名单: {field}")
    if time_range.relative:
        start, end = _relative_window(time_range.relative, datetime.now(UTC))
    else:
        start, end = time_range.start, time_range.end
    if start is None and end is None:
        raise ToolValidationError("time_range 需要 relative 或 start/end")
    filters: list[Filter] = []
    if start is not None:
        filters.append(Filter(field=field, op=">=", value=start))
    if end is not None:
        filters.append(Filter(field=field, op="<=", value=end))
    return filters

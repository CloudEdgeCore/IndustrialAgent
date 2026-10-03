"""TimeSeries Tool 注册与实现（只读，参数化查询）。"""

from datetime import UTC, datetime, timedelta

from tools.base import ToolContext, ToolResult
from tools.freshness import data_freshness
from tools.registry import default_registry
from tools.sql.engine import run_readonly_query
from tools.sql.validator import validate_sql
from tools.timeseries.models import (
    BUCKET_AGGS,
    BUCKETS,
    MAX_RAW_LIMIT,
    TimeSeriesParams,
)
from tools.timeutils import relative_window

_TABLE_BY_KIND = {
    "sensor": ("sensor_readings", "equipment_id", "sensor_type"),
    "process": ("process_parameters", "line_id", "parameter_name"),
}


def _resolve_range(
    params: TimeSeriesParams, anchor: datetime | None = None
) -> tuple[datetime, datetime]:
    """解析查询时间窗口；anchor 为相对时间的"现在"（None → 真实时钟）。"""
    now = anchor or datetime.now(UTC)
    if params.start is None and params.end is None:
        return relative_window(params.relative or "last_24h", now)
    end = params.end or now
    start = params.start or (end - timedelta(hours=24))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return start, end


def _base_where(params: TimeSeriesParams) -> tuple[str, dict]:
    table, entity_col, metric_col = _TABLE_BY_KIND[params.kind]
    where = (
        f"FROM {table} WHERE {entity_col} = %(entity)s "
        f"AND {metric_col} = %(metric)s "
        f"AND timestamp >= %(start)s AND timestamp <= %(end)s"
    )
    sql_params = {"entity": params.entity_id, "metric": params.metric}
    return where, sql_params


def build_series_sql(
    params: TimeSeriesParams, anchor: datetime | None = None
) -> tuple[str, dict, str, datetime, datetime]:
    start, end = _resolve_range(params, anchor)
    where, sql_params = _base_where(params)
    sql_params["start"] = start
    sql_params["end"] = end

    if params.bucket:
        agg = BUCKET_AGGS[params.agg]
        bucket = BUCKETS[params.bucket]
        sql = (
            f"SELECT time_bucket('{bucket}', timestamp) AS bucket, "
            f"{agg}(value) AS value, min(value) AS min_value, "
            f"max(value) AS max_value, count(*) AS point_count "
            f"{where} GROUP BY 1 ORDER BY 1 LIMIT {params.limit}"
        )
    else:
        sql = (
            f"SELECT timestamp, value, quality {where} "
            f"ORDER BY timestamp ASC LIMIT {params.limit}"
        )
    table = _TABLE_BY_KIND[params.kind][0]
    return sql, sql_params, table, start, end


def build_stats_sql(
    params: TimeSeriesParams, anchor: datetime | None = None
) -> tuple[str, dict, str, datetime, datetime]:
    start, end = _resolve_range(params, anchor)
    where, sql_params = _base_where(params)
    sql_params["start"] = start
    sql_params["end"] = end
    sql = (
        "SELECT count(*) AS point_count, min(value) AS min_value, "
        "max(value) AS max_value, avg(value) AS avg_value, "
        "stddev(value) AS stddev_value, first(value, timestamp) AS first_value, "
        f"last(value, timestamp) AS last_value {where}"
    )
    table = _TABLE_BY_KIND[params.kind][0]
    return sql, sql_params, table, start, end


def build_anomaly_sql(
    params: TimeSeriesParams, anchor: datetime | None = None
) -> tuple[str, dict, str, datetime, datetime]:
    start, end = _resolve_range(params, anchor)
    where, sql_params = _base_where(params)
    sql_params["start"] = start
    sql_params["end"] = end
    sql_params["threshold"] = params.threshold
    op = ">" if params.direction == "above" else "<"
    sql = (
        f"SELECT timestamp, value {where} AND value {op} %(threshold)s "
        f"ORDER BY timestamp ASC LIMIT {MAX_RAW_LIMIT}"
    )
    table = _TABLE_BY_KIND[params.kind][0]
    return sql, sql_params, table, start, end


def _group_windows(rows: list[dict], params: TimeSeriesParams) -> list[dict]:
    windows: list[dict] = []
    current: list[dict] = []
    for row in rows:
        if current and row["timestamp"] - current[-1]["timestamp"] > timedelta(minutes=2):
            windows.append(_close_window(current, params))
            current = []
        current.append(row)
    if current:
        windows.append(_close_window(current, params))
    return [
        window
        for window in windows
        if window["duration_minutes"] >= params.min_duration_minutes
    ]


def _close_window(rows: list[dict], params: TimeSeriesParams) -> dict:
    values = [row["value"] for row in rows]
    start, end = rows[0]["timestamp"], rows[-1]["timestamp"]
    peak = max(values) if params.direction == "above" else min(values)
    return {
        "start": start,
        "end": end,
        "duration_minutes": int((end - start).total_seconds() // 60) + 1,
        "peak_value": round(peak, 3),
        "avg_value": round(sum(values) / len(values), 3),
        "point_count": len(rows),
    }


@default_registry.register(
    name="timeseries.query",
    description=(
        "查询设备传感器（sensor）或产线工艺参数（process）时序数据："
        "series=时间序列（可聚合）、stats=统计量、anomaly_windows=阈值异常时间段。"
    ),
    params_model=TimeSeriesParams,
)
def timeseries_query(params: TimeSeriesParams, ctx: ToolContext) -> ToolResult:
    freshness = data_freshness()
    anchor = freshness.anchor
    if params.op == "stats":
        sql, sql_params, table, start, end = build_stats_sql(params, anchor)
    elif params.op == "anomaly_windows":
        sql, sql_params, table, start, end = build_anomaly_sql(params, anchor)
    else:
        sql, sql_params, table, start, end = build_series_sql(params, anchor)

    validate_sql(sql, allowed_tables={table})
    rows = run_readonly_query(sql, sql_params)

    if params.op == "anomaly_windows":
        windows = _group_windows(rows, params)
        data: object = windows
        row_count = len(windows)
    else:
        data = rows
        row_count = len(rows)

    return ToolResult(
        tool="timeseries.query",
        data=data,
        meta={
            "source": f"postgres:{table}",
            "row_count": row_count,
            "sql": sql,
            "entity_id": params.entity_id,
            "metric": params.metric,
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "op": params.op,
            # 证据可追溯：相对时间窗口需能还原到绝对时间与数据新鲜度
            "window": {
                "anchor": anchor.isoformat(),
                "anchor_source": freshness.resolved_from,
                "data_lag_hours": freshness.lag_hours,
            },
        },
    )

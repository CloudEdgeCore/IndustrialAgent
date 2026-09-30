"""TimeSeries Tool 单元测试：参数校验 / SQL 构造 / 权限。"""

import pytest

from tools.base import PermissionDeniedError, ToolContext, ToolValidationError
from tools.executor import execute_tool
from tools.registry import default_registry
from tools.timeseries import tool as _tool  # noqa: F401  触发注册
from tools.timeseries.models import TimeSeriesParams
from tools.timeseries.tool import build_anomaly_sql, build_series_sql, build_stats_sql


def test_registered() -> None:
    assert "timeseries.query" in default_registry.names()


def test_entity_and_metric_validation() -> None:
    # 规范化：eq3 / EQ003 / line-02 → EQ-003 / LINE-2（真实 LLM 常见写法）
    assert (
        TimeSeriesParams(kind="sensor", entity_id="eq3", metric="temperature").entity_id
        == "EQ-003"
    )
    assert (
        TimeSeriesParams(kind="sensor", entity_id="EQ005", metric="Temperature").metric
        == "temperature"
    )
    assert (
        TimeSeriesParams(kind="process", entity_id="line-02", metric="valve").entity_id
        == "LINE-2"
    )
    # 指标别名：coolant_flow → flow
    assert (
        TimeSeriesParams(kind="sensor", entity_id="EQ-003", metric="coolant_flow").metric
        == "flow"
    )
    # 灵活相对时间：last_3h 合法 / 非法值报错
    TimeSeriesParams(
        kind="sensor", entity_id="EQ-003", metric="temperature", relative="last_3h"
    )
    with pytest.raises(ValueError, match="非法相对时间"):
        TimeSeriesParams(
            kind="sensor", entity_id="EQ-003", metric="temperature", relative="just_now"
        )
    # 非法输入仍拒绝
    with pytest.raises(ValueError, match="非法设备编号"):
        TimeSeriesParams(
            kind="sensor", entity_id="EQ-003; DROP TABLE x", metric="temperature"
        )
    with pytest.raises(ValueError, match="非法传感器指标"):
        TimeSeriesParams(kind="sensor", entity_id="EQ-003", metric="power")
    with pytest.raises(ValueError, match="非法产线编号"):
        TimeSeriesParams(kind="process", entity_id="LINE-22", metric="pressure")
    with pytest.raises(ValueError, match="非法工艺参数"):
        TimeSeriesParams(kind="process", entity_id="LINE-2", metric="torque")


def test_anomaly_requires_threshold() -> None:
    with pytest.raises(ValueError, match="需要 threshold"):
        TimeSeriesParams(
            kind="sensor",
            entity_id="EQ-003",
            metric="temperature",
            op="anomaly_windows",
        )


def test_range_validation() -> None:
    with pytest.raises(ValueError, match="start 必须早于 end"):
        TimeSeriesParams(
            kind="sensor",
            entity_id="EQ-003",
            metric="temperature",
            start="2026-09-29T12:00:00+00:00",
            end="2026-09-29T10:00:00+00:00",
        )


def test_series_sql_is_parameterized() -> None:
    params = TimeSeriesParams(
        kind="sensor", entity_id="EQ-003", metric="temperature", relative="last_24h"
    )
    sql, sql_params, table, start, end = build_series_sql(params)
    assert table == "sensor_readings"
    assert "equipment_id = %(entity)s" in sql
    assert "sensor_type = %(metric)s" in sql
    assert sql_params["entity"] == "EQ-003"
    assert start < end


def test_bucket_sql_uses_whitelisted_literals() -> None:
    params = TimeSeriesParams(
        kind="sensor",
        entity_id="EQ-003",
        metric="temperature",
        bucket="5m",
        agg="avg",
    )
    sql, _, _, _, _ = build_series_sql(params)
    assert "time_bucket('5 minutes', timestamp)" in sql
    assert "avg(value) AS value" in sql


def test_stats_and_anomaly_sql() -> None:
    params = TimeSeriesParams(kind="sensor", entity_id="EQ-003", metric="temperature")
    stats_sql, _, _, _, _ = build_stats_sql(params)
    assert "first(value, timestamp)" in stats_sql
    assert "last(value, timestamp)" in stats_sql

    anomaly_params = TimeSeriesParams(
        kind="sensor",
        entity_id="EQ-003",
        metric="temperature",
        op="anomaly_windows",
        threshold=85,
        direction="above",
    )
    anomaly_sql, sql_params, _, _, _ = build_anomaly_sql(anomaly_params)
    assert "value > %(threshold)s" in anomaly_sql
    assert sql_params["threshold"] == 85


def test_permission_matrix() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "EQ-003", "metric": "temperature"},
            ToolContext(agent="router"),
        )
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "EQ-003", "metric": "temperature"},
            ToolContext(agent="report"),
        )


def test_executor_wraps_validation_error() -> None:
    with pytest.raises(ToolValidationError):
        execute_tool(
            "timeseries.query",
            {"kind": "sensor", "entity_id": "DROP", "metric": "temperature"},
            ToolContext(agent="equipment"),
        )

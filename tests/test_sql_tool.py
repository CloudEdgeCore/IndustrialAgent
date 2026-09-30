"""SQL Tool 单元测试：Planner / Builder / Validator / 注入拦截 / 报警查询（离线）。"""

from datetime import UTC, datetime

import pytest

from tools.base import PermissionDeniedError, ToolContext, ToolValidationError
from tools.executor import execute_tool
from tools.registry import default_registry
from tools.sql import domain as _domain  # noqa: F401  触发注册
from tools.sql import tool as _tool  # noqa: F401  触发注册
from tools.sql.builder import build
from tools.sql.models import Filter, Metric, OrderBy, StructuredQuery, TimeRange
from tools.sql.planner import MAX_LIMIT, plan
from tools.sql.validator import validate_sql


def test_tools_registered() -> None:
    names = default_registry.names()
    assert "sql.query" in names
    assert "sql.alarm_search" in names
    assert "sql.history_case" in names


def test_build_basic_query() -> None:
    planned = plan(
        StructuredQuery(
            dataset="equipment",
            select=["equipment_id", "status"],
            filters=[Filter(field="status", op="=", value="alarm")],
            limit=10,
        )
    )
    sql, params = build(planned)
    assert sql.startswith("SELECT equipment_id, status FROM equipment")
    assert "WHERE status = %(p0)s" in sql
    assert params == {"p0": "alarm"}
    assert sql.endswith("LIMIT 10")
    validate_sql(sql, allowed_tables={"equipment"})


def test_unknown_dataset_rejected() -> None:
    with pytest.raises(ToolValidationError, match="未知数据集"):
        plan(StructuredQuery(dataset="pg_shadow"))


def test_unknown_column_rejected() -> None:
    with pytest.raises(ToolValidationError, match="字段不在白名单"):
        plan(StructuredQuery(dataset="equipment", select=["password_hash"]))
    with pytest.raises(ToolValidationError, match="过滤字段不在白名单"):
        plan(
            StructuredQuery(
                dataset="equipment",
                filters=[Filter(field="1=1; --", op="=", value="x")],
            )
        )


def test_stringified_structures_are_parsed() -> None:
    """真实 LLM 常见：time_range / filters 被序列化为 JSON 字符串。"""
    planned = plan(
        StructuredQuery(
            dataset="alarms",
            filters='[{"field": "equipment_id", "op": "=", "value": "EQ-003"}]',
            time_range='{"relative": "yesterday"}',
        )
    )
    sql, _ = build(planned)
    assert "equipment_id = %(p0)s" in sql
    assert "occurred_at >= %(p1)s" in sql


def test_field_and_op_aliases() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms",
            filters=[
                Filter(
                    field="triggered_at",
                    op="gte",
                    value="2026-09-29T00:00:00+00:00",
                )
            ],
            order_by=[OrderBy(field="alarm_id", desc=True)],
            limit=5,
        )
    )
    sql, _ = build(planned)
    assert "occurred_at >=" in sql
    assert "ORDER BY id DESC" in sql

    planned2 = plan(
        StructuredQuery(dataset="equipment", order_by=[OrderBy(field="timestamp")])
    )
    sql2, _ = build(planned2)
    assert "ORDER BY created_at" in sql2


def test_in_op_string_value_and_like_alias() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms",
            filters=[Filter(field="equipment_id", op="in", value="EQ-001, EQ-002")],
        )
    )
    _, params = build(planned)
    assert params["p0"] == ["EQ-001", "EQ-002"]

    planned2 = plan(
        StructuredQuery(
            dataset="quality_inspections",
            filters=[Filter(field="defect_type", op="contains", value="裂纹")],
        )
    )
    sql2, params2 = build(planned2)
    assert "ILIKE" in sql2
    assert params2["p0"] == "%裂纹%"


def test_metric_func_aliases() -> None:
    planned = plan(
        StructuredQuery(
            dataset="quality_inspections",
            group_by=["result"],
            metrics=[Metric(func="mean", field="process_temperature")],
        )
    )
    sql, _ = build(planned)
    assert "avg(process_temperature)" in sql


def test_metric_must_be_numeric() -> None:
    with pytest.raises(ToolValidationError, match="数值列"):
        plan(
            StructuredQuery(
                dataset="equipment", metrics=[Metric(func="avg", field="status")]
            )
        )


def test_group_by_auto_count() -> None:
    planned = plan(StructuredQuery(dataset="quality_inspections", group_by=["result"]))
    sql, _ = build(planned)
    assert "count(*) AS count" in sql
    assert "GROUP BY result" in sql


def test_limit_is_capped() -> None:
    planned = plan(StructuredQuery(dataset="equipment", limit=99999))
    assert planned.limit == MAX_LIMIT
    sql, _ = build(planned)
    assert sql.endswith(f"LIMIT {MAX_LIMIT}")


def test_time_range_relative_adds_filter() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms", time_range=TimeRange(relative="last_24h"), limit=5
        )
    )
    sql, params = build(planned)
    assert "occurred_at >= %(p0)s" in sql
    assert isinstance(params["p0"], datetime)
    assert params["p0"].tzinfo is not None


def test_time_range_flexible_relative() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms", time_range=TimeRange(relative="last_2h"), limit=5
        )
    )
    sql, params = build(planned)
    assert "occurred_at >= %(p0)s" in sql
    assert isinstance(params["p0"], datetime)

    with pytest.raises(ToolValidationError, match="未知时间范围"):
        plan(StructuredQuery(dataset="alarms", time_range=TimeRange(relative="last_2x")))


def test_time_range_explicit() -> None:
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 29, tzinfo=UTC)
    planned = plan(
        StructuredQuery(
            dataset="quality_inspections",
            time_range=TimeRange(start=start, end=end),
        )
    )
    sql, params = build(planned)
    assert "inspection_time >= %(p0)s" in sql
    assert "inspection_time <= %(p1)s" in sql
    assert params == {"p0": start, "p1": end}


def test_order_by_whitelist() -> None:
    with pytest.raises(ToolValidationError, match="排序字段不在白名单"):
        plan(
            StructuredQuery(
                dataset="equipment",
                order_by=[OrderBy(field="equipment_id; DROP TABLE x")],
            )
        )


def test_injection_value_stays_parameterized() -> None:
    evil = "'; DROP TABLE equipment; --"
    planned = plan(
        StructuredQuery(
            dataset="equipment",
            filters=[Filter(field="status", op="=", value=evil)],
        )
    )
    sql, params = build(planned)
    assert evil not in sql, "恶意值绝不能出现在 SQL 文本中"
    assert params["p0"] == evil
    validate_sql(sql, allowed_tables={"equipment"})


def test_in_operator_parameterized() -> None:
    planned = plan(
        StructuredQuery(
            dataset="alarms",
            filters=[Filter(field="alarm_code", op="in", value=["E101", "E102"])],
        )
    )
    sql, params = build(planned)
    assert "alarm_code = ANY(%(p0)s)" in sql
    assert params["p0"] == ["E101", "E102"]


def test_validator_rejects_attacks() -> None:
    with pytest.raises(ToolValidationError, match="多语句"):
        validate_sql("SELECT 1; DROP TABLE equipment", allowed_tables={"equipment"})
    with pytest.raises(ToolValidationError, match="只允许 SELECT"):
        validate_sql("DELETE FROM equipment", allowed_tables={"equipment"})
    with pytest.raises(ToolValidationError, match="禁止关键字"):
        validate_sql(
            "SELECT * FROM equipment WHERE 1=1 AND pg_sleep(10) IS NULL",
            allowed_tables={"equipment"},
        )
    with pytest.raises(ToolValidationError, match="表不在白名单"):
        validate_sql("SELECT * FROM pg_shadow", allowed_tables={"equipment"})
    with pytest.raises(ToolValidationError, match="未引用任何白名单表"):
        validate_sql("SELECT 1", allowed_tables={"equipment"})


def test_alarm_lookup_offline() -> None:
    result = execute_tool(
        "sql.alarm_search",
        {"mode": "lookup", "alarm_code": "E102"},
        ToolContext(agent="equipment"),
    )
    assert result.data["found"] is True
    assert result.data["alarm"]["severity"] == "critical"
    assert any("冷却" in cause for cause in result.data["alarm"]["possible_causes"])

    missing = execute_tool(
        "sql.alarm_search",
        {"mode": "lookup", "alarm_code": "E999"},
        ToolContext(agent="equipment"),
    )
    assert missing.data["found"] is False


def test_alarm_lookup_requires_code() -> None:
    with pytest.raises(ToolValidationError, match="需要 alarm_code"):
        execute_tool(
            "sql.alarm_search", {"mode": "lookup"}, ToolContext(agent="equipment")
        )


def test_alarm_search_permission_denied_for_router() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "sql.alarm_search",
            {"mode": "lookup", "alarm_code": "E102"},
            ToolContext(agent="router"),
        )

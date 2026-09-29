"""域查询工具：报警查询（Alarm Search）与历史故障案例（History Case）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from tools.base import ToolContext, ToolResult, ToolValidationError
from tools.registry import default_registry
from tools.sql.builder import build
from tools.sql.engine import run_readonly_query
from tools.sql.models import Filter, StructuredQuery
from tools.sql.planner import plan
from tools.sql.validator import validate_sql

_MAX_LIMIT = 200


class AlarmSearchParams(BaseModel):
    mode: Literal["lookup", "search"] = Field(
        default="lookup", description="lookup=按代码查解释；search=按条件查报警事件"
    )
    alarm_code: str | None = Field(default=None, description="报警代码，如 E102")
    equipment_id: str | None = None
    status: Literal["active", "acknowledged", "cleared"] | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    since: datetime | None = None
    limit: int = 50


class HistoryCaseParams(BaseModel):
    equipment_id: str | None = None
    alarm_code: str | None = Field(default=None, description="关联报警代码")
    keyword: str | None = Field(default=None, description="关键词（描述/根因/措施）")
    limit: int = 20


def _alarm_catalog() -> dict[str, dict]:
    from data.simulator.catalog import load_alarm_catalog

    return {item["code"]: item for item in load_alarm_catalog()}


@default_registry.register(
    name="sql.alarm_search",
    description="查询报警代码说明（lookup）或按条件检索报警事件（search）。",
    params_model=AlarmSearchParams,
)
def alarm_search(params: AlarmSearchParams, ctx: ToolContext) -> ToolResult:
    catalog = _alarm_catalog()

    if params.mode == "lookup":
        if not params.alarm_code:
            raise ToolValidationError("lookup 模式需要 alarm_code")
        item = catalog.get(params.alarm_code.upper())
        return ToolResult(
            tool="sql.alarm_search",
            data={"found": item is not None, "alarm": item},
            meta={
                "source": "fixtures:alarm_catalog",
                "row_count": 1 if item else 0,
                "alarm_code": params.alarm_code.upper(),
            },
        )

    filters: list[Filter] = []
    if params.equipment_id:
        filters.append(Filter(field="equipment_id", op="=", value=params.equipment_id))
    if params.status:
        filters.append(Filter(field="status", op="=", value=params.status))
    if params.severity:
        filters.append(Filter(field="severity", op="=", value=params.severity))
    if params.since:
        filters.append(Filter(field="occurred_at", op=">=", value=params.since))

    query = StructuredQuery(
        dataset="alarms",
        filters=filters,
        limit=max(1, min(params.limit, _MAX_LIMIT)),
    )
    planned = plan(query)
    sql, sql_params = build(planned)
    validate_sql(sql, allowed_tables={"alarms"})
    rows = run_readonly_query(sql, sql_params)
    for row in rows:
        item = catalog.get(row["alarm_code"])
        row["alarm_name"] = item["name"] if item else None
    return ToolResult(
        tool="sql.alarm_search",
        data=rows,
        meta={
            "source": "postgres:alarms + fixtures:alarm_catalog",
            "row_count": len(rows),
            "sql": sql,
        },
    )


@default_registry.register(
    name="sql.history_case",
    description="检索历史维修/故障案例（按设备、报警代码、关键词）。",
    params_model=HistoryCaseParams,
)
def history_case(params: HistoryCaseParams, ctx: ToolContext) -> ToolResult:
    where_parts: list[str] = []
    sql_params: dict = {}
    if params.equipment_id:
        where_parts.append("equipment_id = %(equipment_id)s")
        sql_params["equipment_id"] = params.equipment_id
    if params.alarm_code:
        where_parts.append("related_alarm_code = %(alarm_code)s")
        sql_params["alarm_code"] = params.alarm_code.upper()
    if params.keyword:
        where_parts.append(
            "(description ILIKE %(keyword)s OR root_cause ILIKE %(keyword)s "
            "OR actions ILIKE %(keyword)s)"
        )
        sql_params["keyword"] = f"%{params.keyword}%"

    limit = max(1, min(params.limit, _MAX_LIMIT))
    sql = (
        "SELECT id, equipment_id, maintenance_type, description, root_cause, "
        "actions, technician, related_alarm_code, occurred_at, completed_at "
        "FROM maintenance_records"
    )
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += f" ORDER BY occurred_at DESC LIMIT {limit}"

    validate_sql(sql, allowed_tables={"maintenance_records"})
    rows = run_readonly_query(sql, sql_params)
    return ToolResult(
        tool="sql.history_case",
        data=rows,
        meta={
            "source": "postgres:maintenance_records",
            "row_count": len(rows),
            "sql": sql,
        },
    )

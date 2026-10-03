"""SQL Query Tool 注册（白名单结构化查询）。"""

from tools.base import ToolContext, ToolResult
from tools.freshness import data_freshness
from tools.registry import default_registry
from tools.sql.builder import build
from tools.sql.engine import run_readonly_query
from tools.sql.models import StructuredQuery
from tools.sql.planner import plan


@default_registry.register(
    name="sql.query",
    description=(
        "结构化查询业务数据库（只读）。数据集/字段/算子受白名单约束，"
        "禁止任意 SQL；返回行数据与来源信息。"
    ),
    params_model=StructuredQuery,
)
def sql_query(params: StructuredQuery, ctx: ToolContext) -> ToolResult:
    freshness = data_freshness()
    planned = plan(params, anchor=freshness.anchor)
    sql, sql_params = build(planned)
    rows = run_readonly_query(
        sql, sql_params, allowed_tables={planned.spec.table}
    )
    return ToolResult(
        tool="sql.query",
        data=rows,
        meta={
            "dataset": params.dataset,
            "row_count": len(rows),
            "sql": sql,
            "source": f"postgres:{planned.spec.table}",
            # 证据可追溯：结论引用的相对时间窗口必须能还原到绝对时间
            "window": {
                "anchor": freshness.anchor.isoformat(),
                "anchor_source": freshness.resolved_from,
                "data_lag_hours": freshness.lag_hours,
            },
        },
    )

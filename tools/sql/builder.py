"""SQL Builder：PlannedQuery → 参数化 SQL（值一律走参数，杜绝注入）。"""

from tools.sql.planner import PlannedQuery

_OPS = {"=": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


def build(planned: PlannedQuery) -> tuple[str, dict]:
    params: dict = {}

    if planned.metrics:
        select_parts = list(planned.group_by)
        for metric in planned.metrics:
            alias = metric.alias or (
                metric.func if metric.field == "*" else f"{metric.func}_{metric.field}"
            )
            select_parts.append(f"{metric.func}({metric.field}) AS {alias}")
    else:
        select_parts = list(planned.select)

    where_parts: list[str] = []
    for index, flt in enumerate(planned.filters):
        key = f"p{index}"
        if flt.op == "is_null":
            where_parts.append(
                f"{flt.field} IS NULL" if flt.value else f"{flt.field} IS NOT NULL"
            )
            continue
        if flt.op == "in":
            where_parts.append(f"{flt.field} = ANY(%({key})s)")
            params[key] = list(flt.value)
            continue
        if flt.op == "like":
            where_parts.append(f"{flt.field} ILIKE %({key})s")
            params[key] = f"%{flt.value}%"
            continue
        where_parts.append(f"{flt.field} {_OPS[flt.op]} %({key})s")
        params[key] = flt.value

    sql = f"SELECT {', '.join(select_parts)} FROM {planned.spec.table}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if planned.metrics and planned.group_by:
        sql += " GROUP BY " + ", ".join(planned.group_by)
    if planned.order_by:
        order = ", ".join(
            f"{item.field} {'DESC' if item.desc else 'ASC'}" for item in planned.order_by
        )
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {planned.limit}"
    return sql, params

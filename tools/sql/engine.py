"""只读查询执行（tool_ro 账号 + 语句超时）。"""

from psycopg.rows import dict_row

from tools.db import tool_db_connection


def run_readonly_query(
    sql: str, params: dict, *, statement_timeout_ms: int = 5000
) -> list[dict]:
    with tool_db_connection() as conn:
        conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

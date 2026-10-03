"""只读查询执行：**SQL Validator 强制收口** + tool_ro 账号 + 语句超时。

架构 §7：SQL Builder → **SQL Validator** → 只读库。
Validator 在此处强制调用（而非由各工具自觉调用），因此任何绕过 Builder 的
新查询路径（例如 RAG 检索）也无法跳过白名单校验。
"""

from collections.abc import Sequence
from typing import Any

from psycopg.rows import dict_row

from tools.db import tool_db_connection
from tools.sql.validator import validate_sql

DEFAULT_STATEMENT_TIMEOUT_MS = 5000


def run_readonly_query(
    sql: str,
    params: dict[str, Any] | Sequence[Any],
    *,
    allowed_tables: set[str],
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
) -> list[dict]:
    """校验后执行只读查询。

    allowed_tables 为**必填关键字参数**：调用方必须显式声明本查询允许触达的表，
    否则校验无从进行（宁可调用点啰嗦，也不留静默绕过路径）。
    """
    validate_sql(sql, allowed_tables=allowed_tables)
    with tool_db_connection() as conn:
        conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

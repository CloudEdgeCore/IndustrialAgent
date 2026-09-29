"""SQL Validator：防御性校验（纵深防御，即使 Builder 出现缺陷也要兜底）。

规则：单语句 / 仅 SELECT / 无危险关键字 / 仅白名单表。
"""

import re

from tools.base import ToolValidationError

FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "copy",
    "execute",
    "call",
    "do",
    "vacuum",
    "analyze",
    "merge",
    "comment",
    "pg_read_file",
    "pg_sleep",
    "dblink",
    "lo_import",
    "lo_export",
}

_TABLE_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-zA-Z_]+")


def validate_sql(sql: str, allowed_tables: set[str]) -> None:
    stripped = sql.strip()
    body = stripped[:-1].rstrip() if stripped.endswith(";") else stripped

    if ";" in body:
        raise ToolValidationError("禁止多语句 SQL")
    if not re.match(r"(?is)^select\b", body):
        raise ToolValidationError("只允许 SELECT 查询")

    tokens = {token.lower() for token in _TOKEN_RE.findall(body)}
    forbidden = tokens & FORBIDDEN_KEYWORDS
    if forbidden:
        raise ToolValidationError(f"SQL 包含禁止关键字: {sorted(forbidden)}")

    tables = {match.lower() for match in _TABLE_RE.findall(body)}
    if not tables:
        raise ToolValidationError("SQL 未引用任何白名单表")
    illegal = tables - allowed_tables
    if illegal:
        raise ToolValidationError(f"表不在白名单: {sorted(illegal)}")

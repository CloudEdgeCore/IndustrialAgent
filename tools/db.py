"""数据库连接助手。

- tool_db_connection：只读账号（tool_ro），供查询类 Tool 使用（架构 §15）
- app_db_connection：应用账号，供需要写入的 Tool（如 Report Tool）使用
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from tools.settings import settings


def normalize_database_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def tool_db_connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(normalize_database_url(settings.tool_database_url))
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def app_db_connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(normalize_database_url(settings.database_url))
    try:
        yield conn
    finally:
        conn.close()

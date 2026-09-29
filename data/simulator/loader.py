"""将模拟数据以 COPY 方式高速写入 PostgreSQL。"""

from collections.abc import Iterable, Iterator
from datetime import date, datetime

import psycopg

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://industrial:industrial@localhost:5432/industrial_agent"
)

TRUNCATE_SQL = (
    "TRUNCATE equipment, alarms, maintenance_records, product_batches, "
    "quality_inspections, defects, sensor_readings, process_parameters CASCADE"
)

TABLE_COLUMNS: dict[str, list[str]] = {
    "defects": ["defect_code", "name", "category", "description"],
    "equipment": [
        "equipment_id",
        "name",
        "equipment_type",
        "model",
        "production_line",
        "status",
        "health_score",
        "commissioned_at",
    ],
    "alarms": [
        "alarm_code",
        "equipment_id",
        "severity",
        "status",
        "occurred_at",
        "cleared_at",
        "description",
    ],
    "maintenance_records": [
        "equipment_id",
        "maintenance_type",
        "description",
        "root_cause",
        "actions",
        "technician",
        "related_alarm_code",
        "occurred_at",
        "completed_at",
    ],
    "product_batches": [
        "batch_id",
        "product_id",
        "equipment_id",
        "production_line",
        "shift",
        "started_at",
        "finished_at",
        "quantity",
    ],
    "quality_inspections": [
        "batch_id",
        "product_id",
        "equipment_id",
        "shift",
        "inspection_time",
        "result",
        "defect_type",
        "process_temperature",
        "process_pressure",
    ],
    "sensor_readings": [
        "equipment_id",
        "sensor_type",
        "timestamp",
        "value",
        "quality",
    ],
    "process_parameters": [
        "line_id",
        "parameter_name",
        "timestamp",
        "value",
        "quality",
    ],
}

COPY_ORDER = [
    "defects",
    "equipment",
    "alarms",
    "maintenance_records",
    "product_batches",
    "quality_inspections",
    "sensor_readings",
    "process_parameters",
]


def normalize_database_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def _format(value: object) -> str:
    if value is None:
        return "\\N"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
    return str(value)


def _rows_to_text(
    rows: Iterable[dict | tuple], columns: list[str], batch_size: int
) -> Iterator[str]:
    buffer: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            line = "\t".join(_format(row.get(col)) for col in columns)
        else:
            line = "\t".join(_format(value) for value in row)
        buffer.append(line)
        if len(buffer) >= batch_size:
            yield "\n".join(buffer) + "\n"
            buffer.clear()
    if buffer:
        yield "\n".join(buffer) + "\n"


def copy_rows(
    cur: psycopg.Cursor,
    table: str,
    rows: Iterable[dict | tuple],
    batch_size: int = 50_000,
) -> int:
    columns = TABLE_COLUMNS[table]
    count = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for chunk in _rows_to_text(rows, columns, batch_size):
            copy.write(chunk)
            count += chunk.count("\n")
    return count


def load_all(
    database_url: str, data: dict[str, Iterable[dict | tuple]]
) -> dict[str, int]:
    """清空业务表并写入全部模拟数据，返回各表行数。"""
    counts: dict[str, int] = {}
    with psycopg.connect(normalize_database_url(database_url)) as conn:
        with conn.cursor() as cur:
            cur.execute(TRUNCATE_SQL)
            _ensure_demo_user(cur)
            for table in COPY_ORDER:
                rows = data.get(table)
                if rows is None:
                    continue
                counts[table] = copy_rows(cur, table, rows)
        conn.commit()
    return counts


def _ensure_demo_user(cur: psycopg.Cursor) -> None:
    """演示账号（admin / admin123），已存在则跳过。"""
    from tools.security import hash_password

    cur.execute("SELECT 1 FROM users WHERE username = %s", ("admin",))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users (username, password_hash, display_name, role, is_active) "
            "VALUES (%s, %s, %s, %s, TRUE)",
            ("admin", hash_password("admin123"), "系统管理员", "admin"),
        )

"""时间范围解析（SQL Tool 与 TimeSeries Tool 共用）。"""

from datetime import UTC, datetime, timedelta

RELATIVE_RANGES = (
    "last_1h",
    "last_24h",
    "last_3d",
    "last_7d",
    "last_30d",
    "today",
    "yesterday",
)


def relative_window(
    relative: str, now: datetime | None = None
) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    if relative == "last_1h":
        return now - timedelta(hours=1), now
    if relative == "last_24h":
        return now - timedelta(hours=24), now
    if relative == "last_3d":
        return now - timedelta(days=3), now
    if relative == "last_7d":
        return now - timedelta(days=7), now
    if relative == "last_30d":
        return now - timedelta(days=30), now
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if relative == "today":
        return day0, now
    if relative == "yesterday":
        return day0 - timedelta(days=1), day0
    raise ValueError(f"未知时间范围: {relative}")

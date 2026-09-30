"""时间范围解析（SQL Tool 与 TimeSeries Tool 共用）。

支持命名范围（last_1h/last_24h/last_3d/last_7d/last_30d/today/yesterday）
与灵活模式（last_Nm / last_Nh / last_Nd），适配真实 LLM 的自然表达。
"""

import re
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

_FLEX_RE = re.compile(r"^last_(\d{1,4})([mhd])$")
_UNIT_DELTA = {"m": "minutes", "h": "hours", "d": "days"}


def parse_relative(
    value: str, now: datetime | None = None
) -> tuple[datetime, datetime] | None:
    """解析相对时间；无法识别时返回 None。"""
    now = now or datetime.now(UTC)
    named = {
        "last_1h": timedelta(hours=1),
        "last_24h": timedelta(hours=24),
        "last_3d": timedelta(days=3),
        "last_7d": timedelta(days=7),
        "last_30d": timedelta(days=30),
    }
    if value in named:
        return now - named[value], now
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if value == "today":
        return day0, now
    if value == "yesterday":
        return day0 - timedelta(days=1), day0
    match = _FLEX_RE.match(value)
    if match:
        amount = int(match.group(1))
        delta = timedelta(**{_UNIT_DELTA[match.group(2)]: amount})
        return now - delta, now
    return None


def relative_window(
    relative: str, now: datetime | None = None
) -> tuple[datetime, datetime]:
    window = parse_relative(relative, now)
    if window is None:
        raise ValueError(f"未知时间范围: {relative}")
    return window

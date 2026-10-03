"""数据新鲜度与窗口锚点（解决"演示数据随时间腐烂"的根因）。

设计动机
--------
模拟/回放数据集的时间轴末尾固定在生成时刻。若所有相对时间窗口都锚定
``datetime.now()``，则数据落库数天后：

- "最近 24 小时"会滑出数据集 → 工具返回空结果、图表空白；
- "最近 3 天不良率 4.5%"会退化成基线水平 → 演示场景静默失真；
- 基于相对时间的断言在数天后开始失败（测试腐烂）。

本模块提供**统一窗口锚点**：默认取数据最新时间（``WINDOW_ANCHOR=data``），
因此窗口始终落在数据时间轴上；生产环境接入真实数据流后设为 ``WINDOW_ANCHOR=now``，
窗口回归真实时钟，并由 ``lag_hours`` 暴露数据滞后（配合告警使用）。

锚点结果带 30 秒进程内缓存，避免每次工具调用都做一次 max() 查询。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg import sql

from tools.db import tool_db_connection
from tools.settings import settings

# 各领域的时间列（均为 tool_ro 已授权的表；表名/列名来自本常量，非用户输入）
_DOMAIN_TIME_COLUMNS: dict[str, tuple[str, str]] = {
    "equipment": ("sensor_readings", "timestamp"),
    "process": ("process_parameters", "timestamp"),
    "quality": ("quality_inspections", "inspection_time"),
    "alarm": ("alarms", "occurred_at"),
    "maintenance": ("maintenance_records", "occurred_at"),
}

_CACHE_TTL_SECONDS = 30.0

_cache_lock = threading.Lock()
_cached: Freshness | None = None
_cached_at = 0.0


@dataclass(frozen=True)
class Freshness:
    """数据新鲜度快照。

    anchor       窗口锚点（相对时间的"现在"）
    resolved_from "data"=锚定数据末尾；"now"=锚定真实时钟
    domains      各领域数据最新时间
    """

    anchor: datetime
    resolved_from: str
    domains: dict[str, datetime | None]

    @property
    def lag_hours(self) -> float:
        """数据末尾相对真实时钟的滞后小时数（越大越陈旧）。"""
        delta = datetime.now(UTC) - self.anchor
        return round(max(0.0, delta.total_seconds() / 3600), 2)

    def to_dict(self) -> dict:
        return {
            "anchor": self.anchor.isoformat(),
            "resolved_from": self.resolved_from,
            "lag_hours": self.lag_hours,
            "domains": {
                name: (value.isoformat() if value else None)
                for name, value in self.domains.items()
            },
        }


def _fetch_domain_times() -> dict[str, datetime | None]:
    """一次 UNION ALL 查询取回各领域最新时间。"""
    query = sql.SQL(" UNION ALL ").join(
        sql.SQL("SELECT {name} AS domain, max({col}) AS ts FROM {tbl}").format(
            name=sql.Literal(name),
            col=sql.Identifier(column),
            tbl=sql.Identifier(table),
        )
        for name, (table, column) in _DOMAIN_TIME_COLUMNS.items()
    )
    result: dict[str, datetime | None] = dict.fromkeys(_DOMAIN_TIME_COLUMNS)
    with tool_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            for domain, moment in cur.fetchall():
                result[str(domain)] = moment
    return result


def compute_freshness(now: datetime | None = None) -> Freshness:
    """计算新鲜度（不读缓存）。

    数据库不可用 / 无权限时优雅降级为 ``now``，保证工具层仍可给出明确错误，
    而不是在新颖度探测上抛出无关异常。
    """
    now = now or datetime.now(UTC)
    try:
        domains = _fetch_domain_times()
    except (psycopg.Error, OSError):
        domains = dict.fromkeys(_DOMAIN_TIME_COLUMNS)

    latest = max((value for value in domains.values() if value is not None), default=None)
    if settings.window_anchor == "now" or latest is None:
        return Freshness(anchor=now, resolved_from="now", domains=domains)
    return Freshness(anchor=latest, resolved_from="data", domains=domains)


def data_freshness(force_refresh: bool = False) -> Freshness:
    """带 TTL 缓存的新鲜度快照（工具层与 API 层共用的唯一入口）。"""
    global _cached, _cached_at
    with _cache_lock:
        fresh = _cached is not None and (time.monotonic() - _cached_at) < _CACHE_TTL_SECONDS
        if force_refresh or not fresh:
            _cached = compute_freshness()
            _cached_at = time.monotonic()
        assert _cached is not None
        return _cached


def window_now() -> datetime:
    """相对时间窗口的"现在"：默认数据锚点，``WINDOW_ANCHOR=now`` 时为真实时钟。"""
    return data_freshness().anchor


def reset_cache() -> None:
    """清空缓存（测试与数据重灌后调用）。"""
    global _cached, _cached_at
    with _cache_lock:
        _cached = None
        _cached_at = 0.0

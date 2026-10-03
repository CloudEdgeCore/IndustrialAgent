"""数据新鲜度 / 窗口锚点单元测试（无需数据库）。

覆盖回归点：查询窗口必须锚定数据末尾，否则数据落库数天后
"最近 24 小时"会滑出数据集，工具返回空结果、演示场景静默失真。
"""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tools import freshness
from tools.freshness import Freshness, compute_freshness, data_freshness, window_now
from tools.settings import settings

ANCHOR = datetime(2026, 9, 30, 4, 35, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear_cache():
    freshness.reset_cache()
    yield
    freshness.reset_cache()


def _stub_domains(monkeypatch, values: dict[str, datetime | None]) -> None:
    monkeypatch.setattr(freshness, "_fetch_domain_times", lambda: dict(values))


def test_anchor_is_latest_data_time(monkeypatch) -> None:
    _stub_domains(
        monkeypatch,
        {"equipment": ANCHOR, "quality": ANCHOR - timedelta(hours=1), "alarm": None},
    )
    result = compute_freshness()
    assert result.anchor == ANCHOR
    assert result.resolved_from == "data"


def test_anchor_uses_wall_clock_when_configured(monkeypatch) -> None:
    _stub_domains(monkeypatch, {"equipment": ANCHOR})
    monkeypatch.setattr(settings, "window_anchor", "now")
    now = ANCHOR + timedelta(days=3)
    result = compute_freshness(now=now)
    assert result.anchor == now
    assert result.resolved_from == "now"


def test_anchor_falls_back_to_now_without_data(monkeypatch) -> None:
    _stub_domains(monkeypatch, dict.fromkeys(freshness._DOMAIN_TIME_COLUMNS))
    now = ANCHOR + timedelta(days=2)
    result = compute_freshness(now=now)
    assert result.anchor == now
    assert result.resolved_from == "now"


def test_database_failure_degrades_to_now(monkeypatch) -> None:
    def _boom() -> dict[str, datetime | None]:
        raise psycopg.OperationalError("db down")

    monkeypatch.setattr(freshness, "_fetch_domain_times", _boom)
    now = ANCHOR + timedelta(hours=5)
    result = compute_freshness(now=now)
    assert result.anchor == now
    assert result.resolved_from == "now"


def test_lag_hours_reflects_staleness() -> None:
    old = datetime.now(UTC) - timedelta(hours=50)
    report = Freshness(anchor=old, resolved_from="data", domains={})
    assert 49.9 < report.lag_hours < 50.1


def test_lag_hours_never_negative_for_future_anchor() -> None:
    future = datetime.now(UTC) + timedelta(hours=3)
    assert Freshness(anchor=future, resolved_from="now", domains={}).lag_hours == 0.0


def test_to_dict_is_json_serializable() -> None:
    report = Freshness(
        anchor=ANCHOR, resolved_from="data", domains={"equipment": ANCHOR, "alarm": None}
    )
    payload = report.to_dict()
    assert payload["anchor"] == ANCHOR.isoformat()
    assert payload["resolved_from"] == "data"
    assert payload["domains"]["equipment"] == ANCHOR.isoformat()
    assert payload["domains"]["alarm"] is None


def test_window_now_is_cached_within_ttl(monkeypatch) -> None:
    calls: list[int] = []

    def _counted() -> dict[str, datetime | None]:
        calls.append(1)
        return {"equipment": ANCHOR}

    monkeypatch.setattr(freshness, "_fetch_domain_times", _counted)
    assert window_now() == ANCHOR
    assert window_now() == ANCHOR
    assert len(calls) == 1, "TTL 内应复用缓存"

    data_freshness(force_refresh=True)
    assert len(calls) == 2, "force_refresh 应穿透缓存"

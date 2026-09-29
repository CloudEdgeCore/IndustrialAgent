"""Analysis Tool 单元测试：白名单算子正确性与参数校验（纯内存，无数据库）。"""

import pytest

from tools.analysis import tool as _tool  # noqa: F401  触发注册
from tools.base import PermissionDeniedError, ToolContext, ToolValidationError
from tools.executor import execute_tool
from tools.registry import default_registry

QUALITY_CTX = ToolContext(agent="quality")


def run(op: str, **kwargs) -> object:
    result = execute_tool("analysis.run", {"op": op, **kwargs}, QUALITY_CTX)
    return result.data


def test_registered() -> None:
    assert "analysis.run" in default_registry.names()


def test_describe() -> None:
    data = run("describe", x=[1, 2, 3, 4, 5])
    assert data["count"] == 5
    assert data["mean"] == 3.0
    assert data["median"] == 3.0
    assert data["min"] == 1.0
    assert data["max"] == 5.0


def test_correlation_pearson_and_spearman() -> None:
    linear = run("correlation", x=[1, 2, 3, 4, 5], y=[2, 4, 6, 8, 10])
    assert linear["r"] == pytest.approx(1.0, abs=1e-3)

    cubic = run("correlation", x=[1, 2, 3, 4, 5], y=[1, 8, 27, 64, 125])
    assert cubic["r"] < 0.99
    spearman = run(
        "correlation", x=[1, 2, 3, 4, 5], y=[1, 8, 27, 64, 125], method="spearman"
    )
    assert spearman["r"] == pytest.approx(1.0, abs=1e-3)


def test_correlation_constant_series() -> None:
    data = run("correlation", x=[5, 5, 5], y=[1, 2, 3])
    assert data["r"] is None


def test_zscore_outliers() -> None:
    values = [10.0] * 20 + [100.0]
    data = run("zscore_outliers", x=values, z_threshold=3.0)
    assert len(data) == 1
    assert data[0]["index"] == 20
    assert data[0]["z"] > 3


def test_iqr_outliers() -> None:
    values = [float(v) for v in range(10, 30)] + [500.0]
    data = run("iqr_outliers", x=values)
    assert [item["index"] for item in data] == [20]


def test_trend_direction() -> None:
    up = run("trend", x=list(range(20)))
    assert up["direction"] == "up"
    assert up["slope"] > 0

    down = run("trend", x=list(range(20, 0, -1)))
    assert down["direction"] == "down"

    flat = run("trend", x=[7.0] * 10)
    assert flat["direction"] == "flat"


def test_rolling_mean() -> None:
    data = run("rolling_mean", x=[1, 2, 3, 4, 5], window=3)
    assert data["values"] == [2.0, 3.0, 4.0]
    assert data["last"] == 4.0


def test_isolation_forest_finds_extremes() -> None:
    values = [10.0 + (i % 3) * 0.1 for i in range(50)] + [100.0, -50.0]
    data = run("isolation_forest", x=values, contamination=0.1)
    outlier_indices = {item["index"] for item in data["outliers"]}
    assert 50 in outlier_indices or 51 in outlier_indices
    assert data["outlier_count"] >= 2


def test_pareto() -> None:
    data = run("pareto", labels=["a", "b", "c"], x=[50, 30, 20])
    items = data["items"]
    assert [item["label"] for item in items] == ["a", "b", "c"]
    assert items[-1]["cumulative_pct"] == pytest.approx(100.0, abs=0.1)
    assert data["vital_few_count"] <= 3


def test_group_by_stats() -> None:
    data = run("group_by_stats", labels=["a", "a", "b"], x=[1, 3, 10])
    groups = {row["label"]: row for row in data["groups"]}
    assert groups["a"]["count"] == 2
    assert groups["a"]["mean"] == 2.0
    assert groups["b"]["mean"] == 10.0

    counts_only = run("group_by_stats", labels=["a", "a", "b"])
    assert {row["label"]: row["count"] for row in counts_only["groups"]} == {"a": 2, "b": 1}


def test_validation_errors() -> None:
    with pytest.raises(ToolValidationError):
        run("describe")
    with pytest.raises(ToolValidationError):
        run("correlation", x=[1, 2], y=[1, 2, 3])
    with pytest.raises(ToolValidationError):
        run("pareto", labels=["a"])
    with pytest.raises(ToolValidationError):
        run("describe", x=[1.0] * 50_001)


def test_permission_matrix() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool("analysis.run", {"op": "describe", "x": [1]}, ToolContext(agent="router"))
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "analysis.run", {"op": "describe", "x": [1]}, ToolContext(agent="report")
        )

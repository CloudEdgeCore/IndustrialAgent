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


def test_pareto_vital_few_at_exact_80_percent() -> None:
    """回归：累计恰好 80.0% 时，原实现 `count(<=80)+1` 会多算一项。"""
    data = run("pareto", labels=["a", "b"], x=[8, 2])
    assert data["items"][0]["cumulative_pct"] == pytest.approx(80.0, abs=0.01)
    assert data["vital_few_count"] == 1, "达到 80% 即应封口，不应再多算一项"


def test_pareto_vital_few_when_never_reaching_80() -> None:
    data = run("pareto", labels=["a", "b", "c"], x=[1, 1, 1])
    assert data["items"][-1]["cumulative_pct"] == pytest.approx(100.0, abs=0.01)
    assert data["vital_few_count"] == 3


def test_rank_uses_average_for_ties() -> None:
    import numpy as np

    from tools.analysis.tool import _rank

    assert list(_rank(np.array([1.0, 2.0, 2.0, 3.0]))) == [0.0, 1.5, 1.5, 3.0]


def test_spearman_handles_ties() -> None:
    """回归：序数秩在并列时给出偏高的相关系数（本例会算成 1.0）。"""
    tied = run("correlation", x=[1, 2, 2, 3], y=[1, 2, 3, 4], method="spearman")
    assert tied["r"] == pytest.approx(0.9487, abs=1e-3)
    assert tied["r"] < 1.0

    identical = run("correlation", x=[1, 2, 2, 3], y=[1, 2, 2, 3], method="spearman")
    assert identical["r"] == pytest.approx(1.0, abs=1e-6)


def test_analysis_meta_is_traceable() -> None:
    """可追溯性：analysis.run 也必须给出 source 与 row_count。"""
    from tools.base import ToolContext
    from tools.executor import execute_tool
    from tools.loader import load_all_tools

    load_all_tools()
    list_result = execute_tool(
        "analysis.run",
        {"op": "zscore_outliers", "x": [1.0] * 20 + [99.0]},
        ToolContext(agent="equipment"),
    )
    assert isinstance(list_result.data, list)
    assert list_result.meta["source"] == "inline:analysis_operators"
    assert list_result.meta["row_count"] == len(list_result.data)

    dict_result = execute_tool(
        "analysis.run",
        {"op": "describe", "x": [1.0, 2.0, 3.0]},
        ToolContext(agent="equipment"),
    )
    assert dict_result.meta["source"] == "inline:analysis_operators"
    assert dict_result.meta["row_count"] == 1, "标量/字典结果应记为 1 条，而非 None"


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


def test_series_string_coercion() -> None:
    """真实 LLM 常把数组传成字符串：应容错解析。"""
    data = run("describe", x="[1.0, 2.0, 3.0]")
    assert data["count"] == 3
    assert data["mean"] == 2.0

    data2 = run("correlation", x="1.0,2.0,3.0", y="2,4,6")
    assert data2["r"] == pytest.approx(1.0, abs=1e-3)

    data3 = run("pareto", labels="['a', 'b']", x="[3, 1]")
    assert data3["items"][0]["label"] == "a"


def test_permission_matrix() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool("analysis.run", {"op": "describe", "x": [1]}, ToolContext(agent="router"))
    with pytest.raises(PermissionDeniedError):
        execute_tool(
            "analysis.run", {"op": "describe", "x": [1]}, ToolContext(agent="report")
        )

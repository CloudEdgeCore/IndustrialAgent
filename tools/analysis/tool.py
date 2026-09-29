"""Analysis Tool：白名单统计分析（Pandas/NumPy/scikit-learn），禁止任意代码执行。

能力（架构 §10/§11）：mean/median/std、correlation、z-score、IQR、rolling mean、
trend、Isolation Forest 异常检测、Pareto、group-by。
"""

import numpy as np
from sklearn.ensemble import IsolationForest

from tools.analysis.models import AnalysisParams
from tools.base import ToolContext, ToolResult, ToolValidationError
from tools.registry import default_registry


def _describe(x: np.ndarray) -> dict:
    std = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    return {
        "count": int(len(x)),
        "mean": round(float(np.mean(x)), 4),
        "std": round(std, 4),
        "min": round(float(np.min(x)), 4),
        "max": round(float(np.max(x)), 4),
        "median": round(float(np.median(x)), 4),
        "p25": round(float(np.percentile(x, 25)), 4),
        "p75": round(float(np.percentile(x, 75)), 4),
    }


def _correlation(x: np.ndarray, y: np.ndarray, method: str) -> dict:
    if method == "spearman":
        x = _rank(x)
        y = _rank(y)
    if np.std(x) == 0 or np.std(y) == 0:
        return {"method": method, "r": None, "note": "序列为常量，无法计算相关性"}
    r = float(np.corrcoef(x, y)[0, 1])
    return {"method": method, "r": round(r, 4), "n": int(len(x))}


def _rank(values: np.ndarray) -> np.ndarray:
    order = values.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    return ranks


def _zscore_outliers(x: np.ndarray, threshold: float) -> list[dict]:
    std = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    if std == 0:
        return []
    z = (x - float(np.mean(x))) / std
    indices = np.where(np.abs(z) > threshold)[0]
    return [
        {"index": int(i), "value": round(float(x[i]), 4), "z": round(float(z[i]), 4)}
        for i in indices
    ]


def _iqr_outliers(x: np.ndarray, k: float) -> list[dict]:
    q1, q3 = float(np.percentile(x, 25)), float(np.percentile(x, 75))
    iqr = q3 - q1
    if iqr == 0:
        return []
    low, high = q1 - k * iqr, q3 + k * iqr
    indices = np.where((x < low) | (x > high))[0]
    return [
        {"index": int(i), "value": round(float(x[i]), 4), "bounds": [round(low, 4), round(high, 4)]}
        for i in indices
    ]


def _trend(x: np.ndarray) -> dict:
    t = np.arange(len(x), dtype=float)
    slope, intercept = np.polyfit(t, x, 1)
    fitted = slope * t + intercept
    ss_res = float(np.sum((x - fitted) ** 2))
    ss_tot = float(np.sum((x - np.mean(x)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    std = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    direction = "flat"
    if std > 0:
        if slope > 0.01 * std:
            direction = "up"
        elif slope < -0.01 * std:
            direction = "down"
    return {
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 4),
        "r2": round(r2, 4),
        "direction": direction,
        "n": int(len(x)),
    }


def _rolling_mean(x: np.ndarray, window: int) -> dict:
    kernel = np.ones(window) / window
    smoothed = np.convolve(x, kernel, mode="valid")
    return {
        "window": window,
        "values": [round(float(v), 4) for v in smoothed],
        "last": round(float(smoothed[-1]), 4) if len(smoothed) else None,
    }


def _isolation_forest(x: np.ndarray, contamination: float) -> dict:
    model = IsolationForest(contamination=contamination, random_state=42)
    predictions = model.fit_predict(x.reshape(-1, 1))
    indices = np.where(predictions == -1)[0]
    return {
        "contamination": contamination,
        "outliers": [
            {"index": int(i), "value": round(float(x[i]), 4)} for i in indices
        ],
        "outlier_count": int(len(indices)),
    }


def _pareto(labels: list[str], values: np.ndarray) -> dict:
    order = np.argsort(values)[::-1]
    sorted_values = values[order]
    total = float(np.sum(sorted_values)) or 1.0
    cumulative = np.cumsum(sorted_values) / total * 100
    items = [
        {
            "label": labels[int(i)],
            "value": round(float(sorted_values[idx]), 4),
            "cumulative_pct": round(float(cumulative[idx]), 2),
        }
        for idx, i in enumerate(order)
    ]
    vital_few = sum(1 for item in items if item["cumulative_pct"] <= 80.0) + 1
    return {"items": items, "vital_few_count": min(vital_few, len(items))}


def _group_by_stats(labels: list[str], values: np.ndarray | None) -> dict:
    counts: dict[str, int] = {}
    groups: dict[str, list[float]] = {}
    for index, label in enumerate(labels):
        counts[label] = counts.get(label, 0) + 1
        if values is not None:
            groups.setdefault(label, []).append(float(values[index]))
    rows = []
    for label, count in counts.items():
        row = {"label": label, "count": count}
        items = groups.get(label, [])
        if items:
            row.update(
                {
                    "mean": round(float(np.mean(items)), 4),
                    "sum": round(float(np.sum(items)), 4),
                    "min": round(float(np.min(items)), 4),
                    "max": round(float(np.max(items)), 4),
                }
            )
        rows.append(row)
    rows.sort(key=lambda item: item["count"], reverse=True)
    return {"groups": rows}


@default_registry.register(
    name="analysis.run",
    description=(
        "白名单统计分析：describe/correlation/zscore_outliers/iqr_outliers/trend/"
        "rolling_mean/isolation_forest/pareto/group_by_stats。禁止任意代码执行。"
    ),
    params_model=AnalysisParams,
)
def analysis_run(params: AnalysisParams, ctx: ToolContext) -> ToolResult:
    x = np.asarray(params.x, dtype=float) if params.x is not None else None
    y = np.asarray(params.y, dtype=float) if params.y is not None else None

    if params.op == "describe":
        data: object = _describe(x)
    elif params.op == "correlation":
        data = _correlation(x, y, params.method)
    elif params.op == "zscore_outliers":
        data = _zscore_outliers(x, params.z_threshold)
    elif params.op == "iqr_outliers":
        data = _iqr_outliers(x, params.iqr_k)
    elif params.op == "trend":
        data = _trend(x)
    elif params.op == "rolling_mean":
        data = _rolling_mean(x, params.window)
    elif params.op == "isolation_forest":
        data = _isolation_forest(x, params.contamination)
    elif params.op == "pareto":
        data = _pareto(params.labels or [], x)
    elif params.op == "group_by_stats":
        data = _group_by_stats(params.labels or [], x)
    else:  # pragma: no cover - pydantic 已限制枚举
        raise ToolValidationError(f"未知算子: {params.op}")

    row_count = len(data) if isinstance(data, list) else None
    return ToolResult(
        tool="analysis.run",
        data=data,
        meta={"op": params.op, "n": int(len(x)) if x is not None else None, "row_count": row_count},
    )

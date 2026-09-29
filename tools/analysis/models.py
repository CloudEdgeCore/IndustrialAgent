"""Analysis Tool 参数模型（白名单分析能力，架构 §10）。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_POINTS = 50_000

AnalysisOp = Literal[
    "describe",
    "correlation",
    "zscore_outliers",
    "iqr_outliers",
    "trend",
    "rolling_mean",
    "isolation_forest",
    "pareto",
    "group_by_stats",
]


class AnalysisParams(BaseModel):
    op: AnalysisOp = Field(description="分析算子（白名单）")
    x: list[float] | None = Field(default=None, description="主序列")
    y: list[float] | None = Field(default=None, description="第二序列（相关性分析）")
    labels: list[str] | None = Field(default=None, description="分组标签（pareto/group_by_stats）")
    method: Literal["pearson", "spearman"] = "pearson"
    window: int = Field(default=5, ge=2, le=1000)
    z_threshold: float = Field(default=3.0, gt=0)
    iqr_k: float = Field(default=1.5, gt=0)
    contamination: float = Field(default=0.05, gt=0, lt=0.5)

    @model_validator(mode="after")
    def _validate(self) -> "AnalysisParams":
        needs_x = {
            "describe",
            "zscore_outliers",
            "iqr_outliers",
            "trend",
            "rolling_mean",
            "isolation_forest",
        }
        if self.op in needs_x and not self.x:
            raise ValueError(f"{self.op} 需要非空 x 序列")
        if self.op == "correlation":
            if not self.x or not self.y:
                raise ValueError("correlation 需要 x 与 y 序列")
            if len(self.x) != len(self.y):
                raise ValueError("x 与 y 长度必须一致")
        if self.op in {"pareto", "group_by_stats"} and not self.labels:
            raise ValueError(f"{self.op} 需要 labels")
        if self.op == "pareto" and (not self.x or len(self.x) != len(self.labels or [])):
            raise ValueError("pareto 需要与 labels 等长的 x（计数值）")
        if self.op == "group_by_stats" and self.x is not None and len(self.x) != len(
            self.labels or []
        ):
            raise ValueError("group_by_stats 的 x 与 labels 长度必须一致")
        for name, series in (("x", self.x), ("y", self.y)):
            if series is not None and len(series) > MAX_POINTS:
                raise ValueError(f"{name} 超过上限 {MAX_POINTS} 点")
        return self

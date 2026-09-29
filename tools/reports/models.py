"""Report Tool 参数模型：强制 Evidence-based 输出（架构红线 §4-4）。

问题描述 / 数据范围 / 异常发现 / 根因候选 / 证据 / 排查顺序 / 风险 / 来源，缺一不可。
"""

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class RootCauseCandidate(BaseModel):
    cause: str = Field(min_length=1, description="根因候选")
    confidence: Confidence
    evidence: list[str] = Field(min_length=1, description="该根因对应的证据（至少 1 条）")


class ReportRequest(BaseModel):
    report_type: Literal[
        "equipment_diagnosis", "process_analysis", "quality_analysis", "daily", "weekly"
    ]
    title: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, description="问题描述")
    data_range: str = Field(min_length=1, description="数据范围（设备/时间/数据集）")
    findings: list[str] = Field(min_length=1, description="发现的异常")
    root_causes: list[RootCauseCandidate] = Field(default_factory=list)
    recommendations: list[str] = Field(min_length=1, description="建议排查顺序")
    risk_level: RiskLevel
    sources: list[str] = Field(min_length=1, description="数据来源（表/工具/文档）")
    equipment_id: str | None = None
    task_id: str | None = None

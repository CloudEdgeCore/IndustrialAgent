"""Agent 结构化输出模型（Evidence-based，架构红线 §4-4）。"""

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class RootCause(BaseModel):
    cause: str = Field(min_length=1)
    confidence: Confidence
    evidence: list[str] = Field(min_length=1)


class AgentConclusion(BaseModel):
    summary: str = Field(min_length=1, description="结论摘要")
    findings: list[str] = Field(default_factory=list, description="异常发现")
    root_causes: list[RootCause] = Field(default_factory=list, description="根因候选")
    recommendations: list[str] = Field(default_factory=list, description="建议排查顺序")
    risk_level: RiskLevel = "medium"
    sources: list[str] = Field(default_factory=list, description="数据来源")

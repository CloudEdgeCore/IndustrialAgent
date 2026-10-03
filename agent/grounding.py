"""结论数值 Grounding 校验（架构红线 §4-4：AI 输出必须 Evidence-based）。

为什么需要：Evidence 契约（字段齐备）此前只由 Pydantic 结构性保证，
"每一条结论都必须有数值证据" 仍只是提示词约束 —— 幻觉数值同样能通过 schema。
本模块把结论里的数值与**工具实际返回的 payload** 做比对，产出可量化的
"数值可溯源比例"，把红线条文落成机制而非声明。

设计取舍
--------
- 只校验"看起来像测量值"的数值：带小数点的数，或 ≥10 的整数；
  窗口大小（3 天 / 24 小时）、序号、步骤数等上下文数字不计入，
  否则会把正常回答判成未溯源。
- 用户问题中出现的数值视为给定上下文，不计入校验（重复引用是合理的）。
- 容差匹配：结论常做四舍五入（payload 92.17 → 结论 92.2），
  因此允许相对 1% 或绝对 0.05 的偏差。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

# 结论中的数值 + 其后的量纲。带"上下文量纲"的数值（时长 / 计数 / 序号）不是测量值：
# "连续 24 分钟"、"最近 3 天"、"1 号产线" 都不应与工具 payload 比对。
_CONTEXT_UNITS = (
    "分钟", "小时", "毫秒", "天", "周", "月", "秒",
    "件", "条", "次", "台", "个", "号", "班", "人", "分", "时", "日",
    "mins", "min", "hrs", "hr", "h", "d", "s",
)
_CONCLUSION_NUMBER_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(" + "|".join(_CONTEXT_UNITS) + r")?",
    re.IGNORECASE,
)

# 相对 / 绝对容差
_REL_TOLERANCE = 0.01
_ABS_TOLERANCE = 0.05
# 低于该数值的整数视为上下文数字（窗口、序号、件数），不参与校验
_MIN_MEANINGFUL_INT = 10
# 校验样本少于该数量时不下结论（避免 1 个数字就报警）
_MIN_SAMPLES = 3


@dataclass
class GroundingReport:
    checked: int = 0
    matched: int = 0
    unmatched: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        return self.matched / self.checked if self.checked else 1.0

    @property
    def is_reliable(self) -> bool:
        """样本足够且溯源比例达标才视为可靠。"""
        return self.checked < _MIN_SAMPLES or self.ratio >= 0.8

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ratio": round(self.ratio, 4),
            "is_reliable": self.is_reliable,
        }


def _collect_tool_numbers(tool_payloads: list[str]) -> list[float]:
    values: list[float] = []
    for payload in tool_payloads:
        for token in _NUMBER_RE.findall(payload):
            try:
                values.append(float(token))
            except ValueError:  # pragma: no cover - 正则已保证可解析
                continue
    return values


def _is_meaningful(token: str, unit: str | None) -> bool:
    """带上下文量纲（时长/计数/序号）的数值一律不算测量值。"""
    if unit:
        return False
    if "." in token:
        return True
    try:
        return abs(int(token)) >= _MIN_MEANINGFUL_INT
    except ValueError:  # pragma: no cover
        return False


def _matches(value: float, corpus: list[float]) -> bool:
    for candidate in corpus:
        if abs(candidate - value) <= max(_ABS_TOLERANCE, abs(value) * _REL_TOLERANCE):
            return True
    return False


def _iter_conclusion_text(conclusion: dict[str, Any]):
    yield str(conclusion.get("summary") or "")
    for finding in conclusion.get("findings") or []:
        yield str(finding)
    for candidate in conclusion.get("root_causes") or []:
        yield str(candidate.get("cause") or "")
        for item in candidate.get("evidence") or []:
            yield str(item)


def verify_grounding(
    conclusion: dict[str, Any],
    tool_payloads: list[Any],
    user_query: str = "",
) -> GroundingReport:
    """比对结论数值与工具返回 payload。

    tool_payloads 传入原始工具结果（dict/list/str 均可，内部序列化）。
    """
    serialized: list[str] = []
    for payload in tool_payloads:
        if isinstance(payload, str):
            serialized.append(payload)
        else:
            serialized.append(json.dumps(payload, ensure_ascii=False, default=str))
    corpus = _collect_tool_numbers(serialized)
    given = set(_NUMBER_RE.findall(user_query))

    report = GroundingReport()
    seen: set[str] = set()
    for text in _iter_conclusion_text(conclusion):
        for token, unit in _CONCLUSION_NUMBER_RE.findall(text):
            if token in seen or token in given:
                continue
            seen.add(token)
            if not _is_meaningful(token, unit):
                continue
            report.checked += 1
            if _matches(float(token), corpus):
                report.matched += 1
            else:
                report.unmatched.append(token)
    return report

"""Agent Eval 评测框架（指标口径见下，避免循环论证）。

指标定义
--------
1. 意图路由
   - ``intent_acc``          ：真实 Router（LLM）产出的 task_type 与期望一致 —— **产品指标**
   - ``heuristic_intent_acc``：关键词降级路由的准确率 —— 只代表兜底路径，**不代表 Agent 能力**
2. 工具选择（仅 LLM 模式可测）
   - ``tool_selection_rate`` ：期望工具集合被**完整**覆盖的用例占比（严格）
   - ``tool_recall``         ：期望工具被实际调用的平均比例
   - ``tool_calls_per_case`` ：平均工具调用次数（效率 / 成本信号，非越高越好）
3. 工具调用稳定性
   - ``tool_call_success_rate``：工具调用未报错的比例（稳定性，**不代表选对工具**）
4. 引用
   - ``citation_answer_rate``   ：回答可读内容命中引用关键词 **且** 实际检索过知识库（端到端）
   - ``citation_retriever_rate``：检索器 top-k 命中关键词（检索器诊断指标）

模式差异（重要）
----------------
- **离线模式**（默认，无需 LLM Key，CI 用）：只能验证
  (a) 启发式路由准确率 (b) 期望工具的参数兼容性/可用性 (c) 检索器命中率。
  它**不执行 Agent**，因此不能作为 Agent 质量证据 —— 报告中 ``measures_agent_behavior`` 为 False。
- **LLM 模式**（``--llm``）：跑完整 Router + 专业 Agent 链路，产出上面第 1/2/3/4 组指标。

基线（CLAUDE.md §9）：意图 ≥90% · 工具 ≥95% · 引用 ≥90%
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.router.agent import heuristic_route
from tools.base import ToolContext, ToolError
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.rag.search import search as rag_search

TESTSET_PATH = Path(__file__).parent / "testset.jsonl"
# 两种模式**分开落盘**：离线跑一次就把 LLM 评测证据覆盖掉，等于丢掉可复核凭据
REPORT_PATH = Path(__file__).parent / "report.json"
REPORT_OFFLINE_PATH = Path(__file__).parent / "report-offline.json"

INTENT_BASELINE = 0.90
TOOL_BASELINE = 0.95
CITATION_BASELINE = 0.90

METRIC_DEFINITIONS = {
    "intent_acc": "LLM Router 的 task_type 准确率（产品指标）",
    "heuristic_intent_acc": "关键词降级路由准确率（仅兜底路径，非 Agent 能力）",
    "tool_selection_rate": "期望工具集合被完整覆盖的用例占比（严格）",
    "tool_recall": "期望工具被实际调用的平均比例",
    "tool_call_success_rate": "工具调用未报错比例（稳定性，不代表选对）",
    "tool_availability_rate": "离线模式：期望工具按测试集参数可成功执行的比例",
    "citation_answer_rate": (
        "需要知识库支撑的用例中，回答带上知识库事实且实际检索过的比例（端到端）"
    ),
    "citation_retriever_rate": "检索器 top-k 命中关键词（检索器诊断）",
}


@dataclass
class EvalCase:
    id: str
    query: str
    expected_task_type: str
    expected_agents: list[str] = field(default_factory=list)
    check_tools: list[dict] = field(default_factory=list)
    expect_citation: bool = False
    citation_keywords: list[str] = field(default_factory=list)
    # 显式声明期望工具；缺省时取 check_tools 的工具名（空 check_tools 需显式声明）
    expected_tools: list[str] = field(default_factory=list)

    @property
    def expected_tool_names(self) -> set[str]:
        if self.expected_tools:
            return set(self.expected_tools)
        return {spec["name"] for spec in self.check_tools}


def load_testset(path: Path = TESTSET_PATH) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvalCase(**json.loads(line)))
    return cases


@dataclass
class EvalReport:
    mode: str
    total: int
    measures_agent_behavior: bool
    # 意图
    intent_hits: int
    heuristic_intent_hits: int
    # 工具选择
    tool_selection_hits: int
    tool_selection_measured: int
    tool_recall_sum: float
    # 工具调用稳定性
    tool_calls_total: int
    tool_calls_ok: int
    # 离线工具可用性
    tool_availability_ok: int
    tool_availability_total: int
    # 引用
    citation_answer_hits: int
    citation_answer_total: int
    citation_retriever_hits: int
    citation_retriever_total: int
    # 基础设施/网络导致的用例执行失败数（仍按"未命中"计入，但单独暴露，
    # 让读者能区分"Agent 判断错误"与"这次网络抖动"）
    case_errors: int = 0
    tool_selection_errors: int = 0
    citation_answer_errors: int = 0
    details: list[dict] = field(default_factory=list)

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator else 0.0

    @property
    def intent_accuracy(self) -> float:
        return self._ratio(self.intent_hits, self.total)

    @property
    def heuristic_intent_accuracy(self) -> float:
        return self._ratio(self.heuristic_intent_hits, self.total)

    @property
    def tool_selection_rate(self) -> float:
        return self._ratio(self.tool_selection_hits, self.tool_selection_measured)

    @property
    def tool_recall(self) -> float:
        return self._ratio(self.tool_recall_sum, self.tool_selection_measured)

    @property
    def tool_call_success_rate(self) -> float:
        return self._ratio(self.tool_calls_ok, self.tool_calls_total)

    @property
    def tool_availability_rate(self) -> float:
        return self._ratio(self.tool_availability_ok, self.tool_availability_total)

    @property
    def tool_calls_per_case(self) -> float:
        return self._ratio(self.tool_calls_total, self.total)

    @property
    def citation_answer_rate(self) -> float:
        return self._ratio(self.citation_answer_hits, self.citation_answer_total)

    @property
    def citation_retriever_rate(self) -> float:
        return self._ratio(self.citation_retriever_hits, self.citation_retriever_total)

    # ---- 排除基础设施失败后的指标 ----
    # 上报两组数字：全量（保守，把网络失败也算 Agent 未命中）与有效用例（真实质量）。
    # 只报前者会低估系统能力，只报后者会掩盖失败率。
    @property
    def intent_accuracy_ok(self) -> float:
        return self._ratio(self.intent_hits, self.total - self.case_errors)

    @property
    def tool_selection_rate_ok(self) -> float:
        return self._ratio(
            self.tool_selection_hits, self.tool_selection_measured - self.tool_selection_errors
        )

    @property
    def citation_answer_rate_ok(self) -> float:
        return self._ratio(
            self.citation_answer_hits, self.citation_answer_total - self.citation_answer_errors
        )

    def baseline_metrics(self) -> dict[str, float]:
        """与 CLAUDE.md §9 三项基线对应的指标（全量口径，含基础设施失败）。"""
        if self.measures_agent_behavior:
            return {
                "intent": self.intent_accuracy,
                "tool": self.tool_selection_rate,
                "citation": self.citation_answer_rate,
            }
        return {
            "intent": self.heuristic_intent_accuracy,
            "tool": self.tool_availability_rate,
            "citation": self.citation_retriever_rate,
        }

    def baseline_metrics_ok(self) -> dict[str, float]:
        """排除基础设施失败后的基线指标（Agent 真实质量口径）。"""
        if self.measures_agent_behavior:
            return {
                "intent": self.intent_accuracy_ok,
                "tool": self.tool_selection_rate_ok,
                "citation": self.citation_answer_rate_ok,
            }
        return self.baseline_metrics()

    def meets_baseline(self) -> dict[str, bool]:
        """以**排除基础设施失败**后的指标判定基线，同时披露全量口径。"""
        values = self.baseline_metrics_ok()
        return {
            "intent": values["intent"] >= INTENT_BASELINE,
            "tool": values["tool"] >= TOOL_BASELINE,
            "citation": values["citation"] >= CITATION_BASELINE,
        }

    def summary(self) -> str:
        suffix = f" | 执行失败 {self.case_errors}" if self.case_errors else ""
        if self.measures_agent_behavior:
            return (
                f"[{self.mode}] 意图(LLM) {self.intent_accuracy:.1%} "
                f"({self.intent_hits}/{self.total}) | "
                f"工具选择 {self.tool_selection_rate:.1%} "
                f"({self.tool_selection_hits}/{self.tool_selection_measured}) | "
                f"工具召回 {self.tool_recall:.1%} | "
                f"调用成功率 {self.tool_call_success_rate:.1%} "
                f"({self.tool_calls_ok}/{self.tool_calls_total}) | "
                f"调用次数/用例 {self.tool_calls_per_case:.1f} | "
                f"引用(端到端) {self.citation_answer_rate:.1%} "
                f"({self.citation_answer_hits}/{self.citation_answer_total}) | "
                f"引用(检索器) {self.citation_retriever_rate:.1%} "
                f"({self.citation_retriever_hits}/{self.citation_retriever_total})"
                + suffix
            )
        return (
            f"[{self.mode}] 意图(启发式兜底) {self.heuristic_intent_accuracy:.1%} "
            f"({self.heuristic_intent_hits}/{self.total}) | "
            f"工具可用性 {self.tool_availability_rate:.1%} "
            f"({self.tool_availability_ok}/{self.tool_availability_total}) | "
            f"引用(检索器) {self.citation_retriever_rate:.1%} "
            f"({self.citation_retriever_hits}/{self.citation_retriever_total})"
            + suffix
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "measures_agent_behavior": self.measures_agent_behavior,
            "summary": self.summary(),
            "metric_definitions": METRIC_DEFINITIONS,
            "metrics": {
                "intent_acc": round(self.intent_accuracy, 4),
                "heuristic_intent_acc": round(self.heuristic_intent_accuracy, 4),
                "tool_selection_rate": round(self.tool_selection_rate, 4),
                "tool_recall": round(self.tool_recall, 4),
                "tool_call_success_rate": round(self.tool_call_success_rate, 4),
                "tool_calls_per_case": round(self.tool_calls_per_case, 2),
                "tool_availability_rate": round(self.tool_availability_rate, 4),
                "citation_answer_rate": round(self.citation_answer_rate, 4),
                "citation_retriever_rate": round(self.citation_retriever_rate, 4),
            },
            "baseline_metrics": {
                key: round(value, 4) for key, value in self.baseline_metrics().items()
            },
            "baseline_metrics_excluding_infra_failures": {
                key: round(value, 4) for key, value in self.baseline_metrics_ok().items()
            },
            "meets_baseline": self.meets_baseline(),
            "counts": {
                "total": self.total,
                "case_errors": self.case_errors,
                "tool_selection_measured": self.tool_selection_measured,
                "tool_calls_total": self.tool_calls_total,
                "citation_answer_total": self.citation_answer_total,
                "citation_retriever_total": self.citation_retriever_total,
            },
            "details": self.details,
        }


def _retriever_citation(case: EvalCase) -> bool | None:
    """检索器诊断指标：top-k 内容是否命中引用关键词（不涉及 Agent）。"""
    if not case.expect_citation:
        return None
    try:
        results = rag_search(case.query, top_k=3)
    except Exception:  # noqa: BLE001 - 检索器不可用时不计入分母
        return None
    combined = " ".join(item["content"] for item in results)
    return any(keyword in combined for keyword in case.citation_keywords)


def _answer_text(result: dict[str, Any]) -> str:
    """Agent 面向用户的可读结论（结论摘要 + 异常发现 + 证据 + 最终回答）。"""
    parts: list[str] = [str(result.get("final_answer") or "")]
    for item in result.get("agent_results", []):
        conclusion = item.get("conclusion") or {}
        parts.append(str(conclusion.get("summary") or ""))
        parts.extend(str(value) for value in conclusion.get("findings") or [])
        for candidate in conclusion.get("root_causes") or []:
            parts.append(str(candidate.get("cause") or ""))
            parts.extend(str(value) for value in candidate.get("evidence") or [])
    return " ".join(parts)


def _needs_knowledge_grounding(case: EvalCase) -> bool:
    """该用例是否**要求**知识库支撑（决定是否纳入端到端引用指标）。

    设备/工艺/质量的纯数据问题可以不查知识库，因此不计入严格引用指标；
    知识问答与显式期望 rag.search 的用例必须真的检索并引用知识库。
    """
    return (
        "rag.search" in case.expected_tool_names
        or case.expected_task_type == "knowledge_qa"
    )


def _answer_citation(case: EvalCase, result: dict[str, Any]) -> bool | None:
    """端到端引用：既检索了知识库，关键词又真的进入了回答。

    仅对"要求知识库支撑"的用例计分；其余用例返回 None（不纳入分母）。
    """
    if not case.expect_citation or not _needs_knowledge_grounding(case):
        return None
    called_rag = any(
        item.get("tool") == "rag.search" for item in result.get("tool_results", [])
    )
    text = _answer_text(result)
    return called_rag and any(keyword in text for keyword in case.citation_keywords)


def _run_offline_case(case: EvalCase) -> dict:
    """离线：期望工具的参数兼容性 + 启发式路由 + 检索器命中（不执行 Agent）。"""
    agent = case.expected_agents[0] if case.expected_agents else "equipment"
    tool_outcomes: list[dict] = []
    for spec in case.check_tools:
        try:
            execute_tool(spec["name"], spec.get("args") or {}, ToolContext(agent=agent))
            tool_outcomes.append({"tool": spec["name"], "ok": True})
        except ToolError as exc:
            tool_outcomes.append({"tool": spec["name"], "ok": False, "error": str(exc)})

    decision = heuristic_route(case.query)
    return {
        "id": case.id,
        "intent_expected": case.expected_task_type,
        "heuristic_intent_actual": decision.task_type,
        "heuristic_intent_hit": decision.task_type == case.expected_task_type,
        "tool_outcomes": tool_outcomes,
        "citation_retriever_hit": _retriever_citation(case),
    }


def run_offline_eval(cases: list[EvalCase] | None = None) -> EvalReport:
    """离线评测：不执行 Agent，只验证兜底路由 / 工具可用性 / 检索器。"""
    load_all_tools()
    if cases is None:
        cases = load_testset()
    report = EvalReport(
        mode="offline",
        total=len(cases),
        measures_agent_behavior=False,
        intent_hits=0,
        heuristic_intent_hits=0,
        tool_selection_hits=0,
        tool_selection_measured=0,
        tool_recall_sum=0.0,
        tool_calls_total=0,
        tool_calls_ok=0,
        tool_availability_ok=0,
        tool_availability_total=0,
        citation_answer_hits=0,
        citation_answer_total=0,
        citation_retriever_hits=0,
        citation_retriever_total=0,
    )
    for case in cases:
        detail = _run_offline_case(case)
        report.heuristic_intent_hits += int(detail["heuristic_intent_hit"])
        for outcome in detail["tool_outcomes"]:
            report.tool_availability_total += 1
            report.tool_availability_ok += int(outcome["ok"])
        if detail["citation_retriever_hit"] is not None:
            report.citation_retriever_total += 1
            report.citation_retriever_hits += int(detail["citation_retriever_hit"])
        report.details.append(detail)

    baseline = report.meets_baseline()
    if not all(baseline.values()):
        report.details.append({"note": "基线未达标项", "baseline": baseline})
    return report


def _run_llm_case(case: EvalCase, model: Any) -> dict:
    """LLM：完整 Router + 专业 Agent 链路。"""
    from agent.runner import run_agent

    result = run_agent(case.query, model=model)
    expected = case.expected_tool_names
    called = [item.get("tool") for item in result.get("tool_results", [])]
    called_set = {name for name in called if name}
    covered = expected <= called_set
    recall = len(expected & called_set) / len(expected) if expected else 1.0

    return {
        "id": case.id,
        "query": case.query,
        "intent_expected": case.expected_task_type,
        "intent_actual": result.get("task_type"),
        "intent_hit": result.get("task_type") == case.expected_task_type,
        "expected_agents": case.expected_agents,
        "agents_actual": result.get("agents", []),
        "expected_tools": sorted(expected),
        "tools_called": sorted(called_set),
        "tool_selection_hit": covered,
        "tool_recall": round(recall, 4),
        "tool_calls": len(called),
        "tool_calls_failed": [
            item
            for item in result.get("tool_results", [])
            if item.get("status") != "done"
        ],
        "citation_answer_hit": _answer_citation(case, result),
        "citation_retriever_hit": _retriever_citation(case),
    }


def _failed_case_detail(case: EvalCase, exc: BaseException) -> dict:
    """单用例异常（LLM 超时 / 网络抖动 / 工具崩溃）不应中断整轮评测。

    失败用例按"未命中"计入，并在 details 中保留 error 供人工排查 —— 静默丢弃会
    让指标虚高，直接抛出则会让 40+ 分钟的评测前功尽弃。
    """
    return {
        "id": case.id,
        "query": case.query,
        "error": f"{type(exc).__name__}: {exc}"[:300],
        "intent_expected": case.expected_task_type,
        "intent_actual": None,
        "intent_hit": False,
        "expected_agents": case.expected_agents,
        "agents_actual": [],
        "expected_tools": sorted(case.expected_tool_names),
        "tools_called": [],
        "tool_selection_hit": False,
        "tool_recall": 0.0,
        "tool_calls": 0,
        "tool_calls_failed": [],
        "citation_answer_hit": False if case.expect_citation else None,
        "citation_retriever_hit": _retriever_citation(case),
    }


def _run_llm_case_safe(case: EvalCase, model: Any) -> dict:
    try:
        return _run_llm_case(case, model)
    except Exception as exc:  # noqa: BLE001 - 单用例失败隔离
        return _failed_case_detail(case, exc)


def run_llm_eval(
    cases: list[EvalCase] | None = None,
    model: Any = None,
    workers: int = 1,
) -> EvalReport:
    """LLM 模式：完整 Agent 链路（需 LLM_API_KEY）。

    workers > 1 时按用例并发（每个用例内含串行工具循环）。串行跑 40+ 条用例、
    数百次 LLM 调用在真实网络下需要数十分钟，且单次网络抖动会被 180s 超时 × 2 次
    重试放大成分钟级阻塞 —— 并发 + 单用例隔离使评测在抖动环境下仍可完成。
    """
    from agent.llm import get_chat_model

    model = model or get_chat_model()
    load_all_tools()
    if cases is None:
        cases = load_testset()

    total = len(cases)
    details: list[dict] = []

    def _report_progress(index: int, detail: dict) -> None:
        status = detail.get("error") or (
            f"intent={detail.get('intent_actual')} calls={detail.get('tool_calls')} "
            f"tools_ok={detail.get('tool_selection_hit')}"
        )
        print(f"  [{index}/{total}] {detail['id']} {status}", flush=True)

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run_llm_case_safe, case, model): case for case in cases
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                detail = future.result()
                _report_progress(done, detail)
                details.append(detail)
        order = {case.id: index for index, case in enumerate(cases)}
        details.sort(key=lambda item: order[item["id"]])
    else:
        for index, case in enumerate(cases, start=1):
            detail = _run_llm_case_safe(case, model)
            _report_progress(index, detail)
            details.append(detail)

    return _aggregate_llm_details(details, total)


def _aggregate_llm_details(details: list[dict], total: int) -> EvalReport:
    """把逐用例明细聚合为报告（独立函数：便于从已保存的 details 重新聚合）。"""
    report = EvalReport(
        mode="llm",
        total=total,
        measures_agent_behavior=True,
        intent_hits=0,
        heuristic_intent_hits=0,
        tool_selection_hits=0,
        tool_selection_measured=0,
        tool_recall_sum=0.0,
        tool_calls_total=0,
        tool_calls_ok=0,
        tool_availability_ok=0,
        tool_availability_total=0,
        citation_answer_hits=0,
        citation_answer_total=0,
        citation_retriever_hits=0,
        citation_retriever_total=0,
    )
    for detail in details:
        failed = "error" in detail
        report.case_errors += int(failed)
        if failed and detail.get("expected_tools"):
            report.tool_selection_errors += 1
        if failed and detail.get("citation_answer_hit") is not None:
            report.citation_answer_errors += 1
        report.intent_hits += int(detail["intent_hit"])
        report.heuristic_intent_hits += int(
            heuristic_route(detail["query"]).task_type == detail["intent_expected"]
        )
        if detail["expected_tools"]:
            report.tool_selection_measured += 1
            report.tool_selection_hits += int(detail["tool_selection_hit"])
            report.tool_recall_sum += float(detail["tool_recall"])
        report.tool_calls_total += detail["tool_calls"]
        report.tool_calls_ok += detail["tool_calls"] - len(detail["tool_calls_failed"])
        if detail["citation_answer_hit"] is not None:
            report.citation_answer_total += 1
            report.citation_answer_hits += int(detail["citation_answer_hit"])
        if detail["citation_retriever_hit"] is not None:
            report.citation_retriever_total += 1
            report.citation_retriever_hits += int(detail["citation_retriever_hit"])
        report.details.append(detail)
    return report


def save_report(report: EvalReport, path: Path = REPORT_PATH) -> Path:
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def rescore_report(path: Path = REPORT_PATH) -> EvalReport:
    """从已保存的 report.json 明细重新聚合（不重跑 LLM）。

    用途：指标口径调整后无需再花数十分钟复跑；也便于对历史结果换口径复核。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("measures_agent_behavior"):
        raise ValueError("仅 LLM 模式报告支持重新聚合（离线模式指标不同）")
    details = [item for item in payload.get("details", []) if "id" in item]
    return _aggregate_llm_details(details, len(details))


def _print_failures(report: EvalReport) -> None:
    for item in report.details:
        if "note" in item:
            print("  ", item)
            continue
        if "error" in item:
            print(f"  用例 {item['id']}: 执行失败（计为未命中）{item['error']}")
            continue
        if report.measures_agent_behavior:
            problems = []
            if not item.get("intent_hit"):
                problems.append(f"意图={item.get('intent_actual')}(期望 {item['intent_expected']})")
            if item.get("expected_tools") and not item.get("tool_selection_hit"):
                problems.append(
                    f"工具缺失 {sorted(set(item['expected_tools']) - set(item['tools_called']))}"
                )
            if item.get("tool_calls_failed"):
                problems.append(f"调用失败 {item['tool_calls_failed']}")
            if item.get("citation_answer_hit") is False:
                problems.append("端到端引用未命中")
            if problems:
                print(f"  用例 {item['id']}: " + "; ".join(problems))
        elif not item.get("heuristic_intent_hit"):
            print(
                f"  用例 {item['id']}: 启发式路由={item.get('heuristic_intent_actual')} "
                f"(期望 {item['intent_expected']})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Eval 评测")
    parser.add_argument("--llm", action="store_true", help="使用真实 LLM（需 API Key）")
    parser.add_argument("--limit", type=int, default=0, help="仅评测前 N 条用例（0=全部）")
    parser.add_argument(
        "--workers", type=int, default=1, help="并发用例数（仅 --llm 生效，默认 1）"
    )
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="不重跑，按当前口径重新聚合已有 report.json",
    )
    args = parser.parse_args()

    if args.rescore:
        report = rescore_report()
        print(report.summary())
        print("基线指标(全量):", {k: round(v, 4) for k, v in report.baseline_metrics().items()})
        print(
            "基线指标(排除基础设施失败):",
            {k: round(v, 4) for k, v in report.baseline_metrics_ok().items()},
        )
        print("是否达标:", report.meets_baseline())
        print("报告 ->", save_report(report))
        return

    cases = load_testset()
    if args.limit > 0:
        cases = cases[: args.limit]
    if args.llm:
        report = run_llm_eval(cases, workers=max(1, args.workers))
        target = REPORT_PATH
    else:
        report = run_offline_eval(cases)
        target = REPORT_OFFLINE_PATH
    print(report.summary())
    print("基线指标:", {k: round(v, 4) for k, v in report.baseline_metrics().items()})
    if report.measures_agent_behavior:
        print(
            "基线指标(排除基础设施失败):",
            {k: round(v, 4) for k, v in report.baseline_metrics_ok().items()},
        )
    print("是否达标:", report.meets_baseline())
    if not report.measures_agent_behavior:
        print("注意: 离线模式不执行 Agent，不能作为 Agent 质量证据（用 --llm）")
    _print_failures(report)
    print("报告 ->", save_report(report, target))


if __name__ == "__main__":
    main()

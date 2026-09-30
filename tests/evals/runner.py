"""Agent Eval 评测框架：意图分类 / 工具调用成功率 / RAG 引用正确率。

模式：
- 离线模式（默认）：启发式路由 + 直接执行期望工具 + 直接检索，无需 LLM Key，
  用于 CI 与本地回归（python tests/evals/runner.py）；
- LLM 模式：配置 LLM_API_KEY 后运行完整 Router + Agent 链路，产出真实指标
  （python tests/evals/runner.py --llm）。

基线（CLAUDE.md §9）：意图 ≥90% · 工具 ≥95% · 引用 ≥90%。
"""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from agent.router.agent import heuristic_route
from tools.base import ToolContext, ToolError
from tools.executor import execute_tool
from tools.loader import load_all_tools
from tools.rag.search import search as rag_search

TESTSET_PATH = Path(__file__).parent / "testset.jsonl"
REPORT_PATH = Path(__file__).parent / "report.json"

INTENT_BASELINE = 0.90
TOOL_BASELINE = 0.95
CITATION_BASELINE = 0.90


@dataclass
class EvalCase:
    id: str
    query: str
    expected_task_type: str
    expected_agents: list[str] = field(default_factory=list)
    check_tools: list[dict] = field(default_factory=list)
    expect_citation: bool = False
    citation_keywords: list[str] = field(default_factory=list)


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
    intent_hits: int
    tool_total: int
    tool_success: int
    citation_total: int
    citation_hits: int
    details: list[dict]

    @property
    def intent_accuracy(self) -> float:
        return self.intent_hits / self.total if self.total else 0.0

    @property
    def tool_success_rate(self) -> float:
        return self.tool_success / self.tool_total if self.tool_total else 0.0

    @property
    def citation_accuracy(self) -> float:
        return self.citation_hits / self.citation_total if self.citation_total else 0.0

    def meets_baseline(self) -> dict[str, bool]:
        return {
            "intent": self.intent_accuracy >= INTENT_BASELINE,
            "tool": self.tool_success_rate >= TOOL_BASELINE,
            "citation": self.citation_accuracy >= CITATION_BASELINE,
        }

    def summary(self) -> str:
        return (
            f"[{self.mode}] 意图 {self.intent_accuracy:.1%} "
            f"({self.intent_hits}/{self.total}) | 工具 {self.tool_success_rate:.1%} "
            f"({self.tool_success}/{self.tool_total}) | 引用 {self.citation_accuracy:.1%} "
            f"({self.citation_hits}/{self.citation_total})"
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "summary": self.summary(),
            "intent_accuracy": round(self.intent_accuracy, 4),
            "tool_success_rate": round(self.tool_success_rate, 4),
            "citation_accuracy": round(self.citation_accuracy, 4),
            "meets_baseline": self.meets_baseline(),
            "details": self.details,
        }


def _citation_check(case: EvalCase) -> bool | None:
    if not case.expect_citation:
        return None
    results = rag_search(case.query, top_k=3)
    combined = " ".join(item["content"] for item in results)
    return any(keyword in combined for keyword in case.citation_keywords)


def _tool_check_offline(case: EvalCase) -> list[dict]:
    agent = case.expected_agents[0] if case.expected_agents else "equipment"
    outcomes: list[dict] = []
    for spec in case.check_tools:
        try:
            execute_tool(spec["name"], spec.get("args") or {}, ToolContext(agent=agent))
            outcomes.append({"tool": spec["name"], "ok": True})
        except ToolError as exc:
            outcomes.append({"tool": spec["name"], "ok": False, "error": str(exc)})
    return outcomes


def run_offline_eval(cases: list[EvalCase] | None = None) -> EvalReport:
    load_all_tools()
    cases = cases or load_testset()
    intent_hits = 0
    tool_total = tool_success = 0
    citation_total = citation_hits = 0
    details: list[dict] = []

    for case in cases:
        decision = heuristic_route(case.query)
        intent_hit = decision.task_type == case.expected_task_type
        intent_hits += int(intent_hit)

        outcomes = _tool_check_offline(case)
        tool_total += len(outcomes)
        tool_success += sum(1 for item in outcomes if item["ok"])

        citation_hit = _citation_check(case)
        if citation_hit is not None:
            citation_total += 1
            citation_hits += int(citation_hit)

        details.append(
            {
                "id": case.id,
                "intent_expected": case.expected_task_type,
                "intent_actual": decision.task_type,
                "intent_hit": intent_hit,
                "tools": outcomes,
                "citation_hit": citation_hit,
            }
        )

    return EvalReport(
        mode="offline",
        total=len(cases),
        intent_hits=intent_hits,
        tool_total=tool_total,
        tool_success=tool_success,
        citation_total=citation_total,
        citation_hits=citation_hits,
        details=details,
    )


def run_llm_eval(cases: list[EvalCase] | None = None, model=None) -> EvalReport:
    """LLM 模式：完整 Router + Agent 链路（需 LLM_API_KEY）。"""
    from agent.llm import get_chat_model
    from agent.runner import run_agent

    model = model or get_chat_model()
    load_all_tools()
    cases = cases or load_testset()
    intent_hits = 0
    tool_total = tool_success = 0
    citation_total = citation_hits = 0
    details: list[dict] = []

    for case in cases:
        result = run_agent(case.query, model=model)
        intent_hit = result.get("task_type") == case.expected_task_type
        intent_hits += int(intent_hit)

        outcomes = [
            {"tool": item["tool"], "ok": item["status"] == "done"}
            for item in result.get("tool_results", [])
        ]
        tool_total += len(outcomes)
        tool_success += sum(1 for item in outcomes if item["ok"])

        citation_hit = _citation_check(case)
        if citation_hit is not None:
            citation_total += 1
            citation_hits += int(citation_hit)

        details.append(
            {
                "id": case.id,
                "intent_expected": case.expected_task_type,
                "intent_actual": result.get("task_type"),
                "intent_hit": intent_hit,
                "tools": outcomes,
                "citation_hit": citation_hit,
            }
        )

    return EvalReport(
        mode="llm",
        total=len(cases),
        intent_hits=intent_hits,
        tool_total=tool_total,
        tool_success=tool_success,
        citation_total=citation_total,
        citation_hits=citation_hits,
        details=details,
    )


def save_report(report: EvalReport, path: Path = REPORT_PATH) -> Path:
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Eval 评测")
    parser.add_argument("--llm", action="store_true", help="使用真实 LLM（需 API Key）")
    parser.add_argument("--limit", type=int, default=0, help="仅评测前 N 条用例（0=全部）")
    args = parser.parse_args()

    cases = load_testset()
    if args.limit > 0:
        cases = cases[: args.limit]
    report = run_llm_eval(cases) if args.llm else run_offline_eval(cases)
    print(report.summary())
    print("基线:", report.meets_baseline())
    for item in report.details:
        if not item["intent_hit"] or any(not t["ok"] for t in item["tools"]):
            print(f"  用例 {item['id']}: intent={item['intent_actual']} "
                  f"(期望 {item['intent_expected']}), tools={item['tools']}")
    print("报告 ->", save_report(report))


if __name__ == "__main__":
    main()

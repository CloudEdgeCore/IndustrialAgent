"""Eval 指标口径单元测试（无需数据库 / LLM）。

这些测试锁定指标语义，防止回归到"循环论证"：
- 端到端引用必须要求真正调用过 rag.search 且关键词进入回答；
- 只有"需要知识库支撑"的用例才纳入端到端引用分母；
- 工具选择按**期望工具集合是否被完整覆盖**判定，与调用次数无关；
- 用得再多也不会因为"没报错"而刷高工具选择分。
"""

from evals.runner import (
    METRIC_DEFINITIONS,
    EvalCase,
    EvalReport,
    _answer_citation,
    _answer_text,
    _needs_knowledge_grounding,
)


def _case(**overrides) -> EvalCase:
    base = {
        "id": "T-001",
        "query": "E102 怎么处理？",
        "expected_task_type": "knowledge_qa",
        "expected_agents": ["equipment"],
        "check_tools": [],
        "expected_tools": ["rag.search"],
        "expect_citation": True,
        "citation_keywords": ["E102"],
    }
    base.update(overrides)
    return EvalCase(**base)


def test_expected_tools_prefers_explicit_declaration() -> None:
    case = _case(check_tools=[{"name": "sql.query", "args": {}}])
    assert case.expected_tool_names == {"rag.search"}


def test_expected_tools_falls_back_to_check_tools() -> None:
    case = _case(expected_tools=[], check_tools=[{"name": "timeseries.query", "args": {}}])
    assert case.expected_tool_names == {"timeseries.query"}


def test_answer_text_collects_conclusions_and_findings() -> None:
    result = {
        "final_answer": "已生成报告",
        "agent_results": [
            {
                "conclusion": {
                    "summary": "E102 表示主轴温度过高",
                    "findings": ["温度峰值 92℃"],
                    "root_causes": [{"cause": "冷却液不足", "evidence": ["流量 14.9 L/min"]}],
                }
            }
        ],
    }
    text = _answer_text(result)
    assert "E102 表示主轴温度过高" in text
    assert "温度峰值 92℃" in text
    assert "流量 14.9 L/min" in text


def test_citation_requires_rag_actually_called() -> None:
    case = _case()
    no_rag = {"final_answer": "E102 表示主轴温度过高", "tool_results": []}
    assert _answer_citation(case, no_rag) is False, "没检索知识库不算引用命中"

    with_rag = {
        "final_answer": "E102 表示主轴温度过高",
        "tool_results": [{"tool": "rag.search", "status": "done"}],
    }
    assert _answer_citation(case, with_rag) is True


def test_citation_requires_keyword_in_answer() -> None:
    case = _case()
    result = {
        "final_answer": "请检查冷却系统",
        "tool_results": [{"tool": "rag.search", "status": "done"}],
    }
    assert _answer_citation(case, result) is False


def test_pure_data_case_is_excluded_from_strict_citation() -> None:
    """设备数据问题不强制查知识库，因此不进入严格引用指标分母。"""
    case = _case(
        expected_task_type="equipment_diagnosis",
        expected_tools=["timeseries.query"],
        citation_keywords=["温度"],
    )
    assert _needs_knowledge_grounding(case) is False
    assert _answer_citation(case, {"tool_results": []}) is None


def test_metric_definitions_documented() -> None:
    for key in (
        "intent_acc",
        "heuristic_intent_acc",
        "tool_selection_rate",
        "citation_answer_rate",
        "citation_retriever_rate",
    ):
        assert key in METRIC_DEFINITIONS


def _report(**overrides) -> EvalReport:
    base = dict(
        mode="llm",
        total=10,
        measures_agent_behavior=True,
        intent_hits=9,
        heuristic_intent_hits=5,
        tool_selection_hits=8,
        tool_selection_measured=10,
        tool_recall_sum=9.0,
        tool_calls_total=100,
        tool_calls_ok=99,
        tool_availability_ok=0,
        tool_availability_total=0,
        citation_answer_hits=7,
        citation_answer_total=10,
        citation_retriever_hits=10,
        citation_retriever_total=10,
    )
    base.update(overrides)
    return EvalReport(**base)


def test_report_metrics_are_per_case_not_per_call() -> None:
    report = _report()
    assert report.tool_selection_rate == 0.8, "工具选择按用例计，而非调用次数"
    assert report.tool_recall == 0.9
    assert report.tool_call_success_rate == 0.99
    assert report.tool_calls_per_case == 10.0
    assert report.citation_answer_rate == 0.7
    assert report.citation_retriever_rate == 1.0


def test_many_successful_calls_do_not_inflate_selection_score() -> None:
    """退化解防护：狂调工具且都不报错，工具选择分不会因此变高。"""
    spam = _report(tool_selection_hits=1, tool_calls_total=1000, tool_calls_ok=1000)
    assert spam.tool_selection_rate == 0.1
    assert spam.tool_call_success_rate == 1.0


def test_baseline_metrics_use_agent_metrics_only_when_measured() -> None:
    llm = _report()
    assert llm.baseline_metrics()["intent"] == llm.intent_accuracy
    assert llm.meets_baseline() == {"intent": True, "tool": False, "citation": False}

    offline = _report(
        mode="offline",
        measures_agent_behavior=False,
        heuristic_intent_hits=10,
        tool_availability_ok=10,
        tool_availability_total=10,
        citation_retriever_hits=10,
        citation_retriever_total=10,
    )
    assert offline.baseline_metrics()["intent"] == 1.0
    assert offline.meets_baseline() == {"intent": True, "tool": True, "citation": True}


def test_empty_denominators_do_not_divide_by_zero() -> None:
    empty = _report(
        total=0,
        intent_hits=0,
        heuristic_intent_hits=0,
        tool_selection_hits=0,
        tool_selection_measured=0,
        tool_recall_sum=0.0,
        tool_calls_total=0,
        tool_calls_ok=0,
        citation_answer_hits=0,
        citation_answer_total=0,
        citation_retriever_hits=0,
        citation_retriever_total=0,
    )
    assert empty.intent_accuracy == 0.0
    assert empty.tool_selection_rate == 0.0
    assert empty.citation_answer_rate == 0.0
    assert empty.tool_calls_per_case == 0.0

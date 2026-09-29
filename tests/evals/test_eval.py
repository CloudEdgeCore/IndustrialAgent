"""Eval 评测入口：pytest tests/evals 运行。

- 测试集质量检查（≥30 条、ID 唯一）；
- 离线意图基线（无需数据库）；
- 工具调用与 RAG 引用基线（集成测试，无库自动跳过）。
"""

import pytest
from evals.runner import (
    CITATION_BASELINE,
    INTENT_BASELINE,
    TOOL_BASELINE,
    load_testset,
    run_offline_eval,
)

from agent.router.agent import heuristic_route


def test_testset_quality() -> None:
    cases = load_testset()
    assert len(cases) >= 30, "评测集不得少于 30 条"
    assert len({case.id for case in cases}) == len(cases), "ID 必须唯一"
    for case in cases:
        assert case.query.strip()
        assert case.expected_task_type
        if case.expect_citation:
            assert case.citation_keywords, f"{case.id} 缺少引用关键词"


def test_offline_intent_baseline() -> None:
    cases = load_testset()
    hits = sum(
        1
        for case in cases
        if heuristic_route(case.query).task_type == case.expected_task_type
    )
    accuracy = hits / len(cases)
    assert accuracy >= INTENT_BASELINE, (
        f"离线意图准确率 {accuracy:.1%} 低于基线 {INTENT_BASELINE:.0%}；"
        f"未命中: "
        + ", ".join(
            case.id
            for case in cases
            if heuristic_route(case.query).task_type != case.expected_task_type
        )
    )


@pytest.mark.integration
def test_offline_tools_and_citation_baseline() -> None:
    report = run_offline_eval()
    assert report.tool_success_rate >= TOOL_BASELINE, report.summary()
    assert report.citation_accuracy >= CITATION_BASELINE, report.summary()
    assert report.intent_accuracy >= INTENT_BASELINE, report.summary()

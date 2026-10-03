"""Eval 评测入口：pytest tests/evals 运行。

- 测试集质量检查（≥30 条、ID 唯一、每条声明期望工具、意图全覆盖）——无需数据库；
- 启发式兜底路由基线——无需数据库；
- 工具参数可用性 + 检索器命中基线——**集成测试**（无库自动跳过）。

注意：离线模式**不执行 Agent**，因此不是 Agent 质量证据；真实指标由
``python tests/evals/runner.py --llm`` 产出（需 LLM_API_KEY）。
"""

import os

import psycopg
import pytest
from evals.runner import (
    CITATION_BASELINE,
    INTENT_BASELINE,
    TOOL_BASELINE,
    load_testset,
    run_offline_eval,
)

from agent.router.agent import heuristic_route
from tools.db import normalize_database_url
from tools.settings import settings


@pytest.fixture(scope="module")
def require_db() -> None:
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM equipment")
            if cur.fetchone()[0] == 0:
                pytest.skip("数据未种子化，先执行 python -m data.simulator")
    finally:
        conn.close()


def test_testset_quality() -> None:
    cases = load_testset()
    assert len(cases) >= 30, "评测集不得少于 30 条"
    assert len({case.id for case in cases}) == len(cases), "ID 必须唯一"
    for case in cases:
        assert case.query.strip()
        assert case.expected_task_type
        # 每条用例都必须声明期望工具，否则"工具选择"维度无法度量
        assert case.expected_tool_names, f"{case.id} 缺少期望工具（expected_tools/check_tools）"
        if case.expect_citation:
            assert case.citation_keywords, f"{case.id} 缺少引用关键词"


def test_testset_covers_all_intents() -> None:
    intents = {case.expected_task_type for case in load_testset()}
    assert intents == {
        "equipment_diagnosis",
        "process_analysis",
        "quality_trace",
        "knowledge_qa",
        "mixed",
        "report",
    }, f"意图覆盖不全: {sorted(intents)}"


def test_testset_is_not_answer_shaped() -> None:
    """防退化：测试集不应只覆盖单一数据集/单一工具。"""
    tools = set()
    for case in load_testset():
        tools |= case.expected_tool_names
    assert len(tools) >= 4, f"期望工具覆盖过窄: {sorted(tools)}"


def test_offline_intent_baseline() -> None:
    """启发式兜底路由基线（纯函数，不访问数据库）。"""
    misses = [
        case.id
        for case in load_testset()
        if heuristic_route(case.query).task_type != case.expected_task_type
    ]
    accuracy = 1 - len(misses) / len(load_testset())
    assert accuracy >= INTENT_BASELINE, (
        f"启发式兜底路由准确率 {accuracy:.1%} 低于基线 {INTENT_BASELINE:.0%}；"
        f"未命中: {', '.join(misses)}"
    )


def test_offline_eval_does_not_claim_agent_behavior() -> None:
    """防止再次把"离线自评"当成 Agent 质量证据（指标口径回归防护）。"""
    report = run_offline_eval([])
    assert report.measures_agent_behavior is False
    assert report.tool_selection_measured == 0
    payload = report.to_dict()
    assert payload["measures_agent_behavior"] is False
    assert "metric_definitions" in payload
    assert payload["metrics"]["tool_selection_rate"] == 0.0


@pytest.mark.integration
def test_offline_tools_and_citation_baseline(require_db: None) -> None:
    report = run_offline_eval()
    assert report.tool_availability_rate >= TOOL_BASELINE, report.summary()
    assert report.citation_retriever_rate >= CITATION_BASELINE, report.summary()
    assert report.heuristic_intent_accuracy >= INTENT_BASELINE, report.summary()

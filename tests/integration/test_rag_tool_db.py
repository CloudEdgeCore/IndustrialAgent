"""RAG 集成测试：文档导入 + 混合检索 + 引用正确性（无库自动跳过）。"""

import os

import psycopg
import pytest

from tools.base import ToolContext
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.rag import tool as _tool  # noqa: F401  触发注册
from tools.rag.ingest import ingest_documents
from tools.rag.search import search
from tools.settings import settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_db_and_ingest() -> None:
    url = normalize_database_url(
        os.environ.get("DATABASE_URL", settings.database_url)
    )
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")
    conn.close()
    summary = ingest_documents()
    assert summary["documents"] >= 5
    assert summary["chunks"] >= 10


def test_e102_query_cites_correct_docs() -> None:
    results = search("E102 报警应该怎么处理", top_k=3)
    assert len(results) == 3
    top = results[0]
    assert "E102" in top["content"]
    assert top["document_type"] in {"sop", "alarm_code", "manual"}
    assert top["document_title"]
    assert top["chunk_index"] >= 0
    assert top["section"]
    assert "rerank" in top["scores"]


def test_coolant_query_hits_manual_or_sop() -> None:
    results = search("主轴冷却液流量下降怎么排查", top_k=3)
    combined = " ".join(item["content"] for item in results)
    assert "冷却" in combined
    assert any(
        item["document_title"].startswith(("X200", "E102")) for item in results
    )


def test_document_type_filter() -> None:
    results = search("温度 报警 处理", top_k=5, document_type="sop")
    assert results
    assert all(item["document_type"] == "sop" for item in results)


def test_injection_query_hits_injection_sop() -> None:
    results = search("注塑机料筒温度怎么设置", top_k=3)
    assert any("注塑机" in item["document_title"] for item in results)


def test_rag_search_via_executor() -> None:
    result = execute_tool(
        "rag.search",
        {"query": "表面裂纹怎么判定", "top_k": 3, "document_type": "quality"},
        ToolContext(agent="quality"),
    )
    assert result.meta["row_count"] >= 1
    assert result.meta["source"] == "postgres:document_chunks"
    assert "裂纹" in result.data[0]["content"]


def test_keyword_arm_ranking_is_deterministic() -> None:
    """回归：关键词臂缺 ORDER BY 时 LIMIT 截取堆序行，排序不可复现。"""
    query = "主轴 温度 冷却 流量 报警 处理"
    first = [item["chunk_id"] for item in search(query, top_k=5)]
    for _ in range(3):
        assert [item["chunk_id"] for item in search(query, top_k=5)] == first


def test_keyword_relevance_beats_arbitrary_order() -> None:
    """命中 token 更多的分块应排到更前（同分时按 c.id 兜底）。"""
    results = search("主轴 温度 冷却 流量", top_k=5)
    hits = [item["scores"]["keyword_hits"] for item in results]
    assert hits == sorted(hits, reverse=True), f"相关度未按降序排列: {hits}"


def test_retrieval_indexes_exist() -> None:
    """HNSW（向量）与 pg_trgm（关键词 ILIKE）索引必须存在。"""
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'document_chunks'"
        )
        names = {row[0] for row in cur.fetchall()}
    assert "ix_document_chunks_embedding_hnsw" in names
    assert "ix_document_chunks_content_trgm" in names

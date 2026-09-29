"""RAG 单元测试：解析 / 分块 / 确定性 Embedding / 向量字面量 / 权限（无数据库）。"""

from pathlib import Path

import numpy as np
import pytest

from tools.base import PermissionDeniedError, ToolContext, ToolValidationError
from tools.executor import execute_tool
from tools.rag import tool as _tool  # noqa: F401  触发注册
from tools.rag.embedding import DeterministicEmbedding, get_embedding_provider, tokenize
from tools.rag.parser import ParsedDocument, chunk_document, parse_document
from tools.rag.search import _vector_literal
from tools.registry import default_registry

SAMPLE = """---
title: 测试手册
document_type: manual
equipment_type: cnc
version: V1.0
---

# 测试手册

## 1. 温度检查

主轴温度正常范围 40~80℃。超过 85℃ 触发 E102 报警。

## 2. 冷却系统

冷却液流量标准 18 L/min。
"""


def test_parse_document(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(SAMPLE, encoding="utf-8")
    doc = parse_document(path)
    assert doc.title == "测试手册"
    assert doc.document_type == "manual"
    assert doc.equipment_type == "cnc"
    assert doc.version == "V1.0"
    assert len(doc.sections) == 2
    assert doc.sections[0][0] == "1. 温度检查"


def test_chunk_document_respects_size_and_section() -> None:
    long_paragraph = "温" * 1500
    doc = ParsedDocument(
        title="t",
        document_type="manual",
        equipment_type=None,
        equipment_model=None,
        version=None,
        source_file="t.md",
        sections=[("1. 长文本", long_paragraph), ("2. 短文本", "短内容")],
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 3
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.content) <= 600 for chunk in chunks)
    assert chunks[0].section == "1. 长文本"
    assert chunks[-1].section == "2. 短文本"


def test_tokenize_mixed_text() -> None:
    tokens = tokenize("E102 主轴温度过高")
    assert "e102" in tokens
    assert "主轴" in tokens
    assert "温度" in tokens


def test_deterministic_embedding_reproducible_and_overlap_sensitive() -> None:
    provider = DeterministicEmbedding(dim=256)
    first = provider.embed(["E102 主轴温度过高处理流程"])[0]
    second = provider.embed(["E102 主轴温度过高处理流程"])[0]
    assert first == second

    related = provider.embed(["E102 报警处理与记录要求"])[0]
    unrelated = provider.embed(["注塑机料筒温度设置方法"])[0]

    def cosine(a: list[float], b: list[float]) -> float:
        va, vb = np.asarray(a), np.asarray(b)
        return float(va @ vb)

    assert cosine(first, related) > cosine(first, unrelated)


def test_default_provider_is_deterministic() -> None:
    provider = get_embedding_provider()
    assert isinstance(provider, DeterministicEmbedding)


def test_vector_literal_format() -> None:
    literal = _vector_literal([0.5, -1.25])
    assert literal == "[0.50000000,-1.25000000]"


def test_rag_tool_registered_and_validation() -> None:
    assert "rag.search" in default_registry.names()

    with pytest.raises(ToolValidationError):
        execute_tool("rag.search", {"query": ""}, ToolContext(agent="equipment"))
    with pytest.raises(ToolValidationError):
        execute_tool(
            "rag.search", {"query": "E102", "top_k": 99}, ToolContext(agent="equipment")
        )


def test_rag_permission_matrix() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool("rag.search", {"query": "E102"}, ToolContext(agent="router"))
    with pytest.raises(PermissionDeniedError):
        execute_tool("rag.search", {"query": "E102"}, ToolContext(agent="report"))

"""RAG Search Tool 注册（混合检索 + 引用元数据）。"""

from typing import Literal

from pydantic import BaseModel, Field

from tools.base import ToolContext, ToolResult
from tools.rag.search import search
from tools.registry import default_registry


class RagSearchParams(BaseModel):
    query: str = Field(min_length=1, max_length=500, description="检索问题")
    top_k: int = Field(default=5, ge=1, le=10)
    document_type: Literal[
        "manual", "sop", "alarm_code", "quality", "maintenance", "standard"
    ] | None = None
    equipment_type: Literal["cnc", "injection_molding", "assembly_line"] | None = None


@default_registry.register(
    name="rag.search",
    description=(
        "工业知识库检索（向量 + 关键词混合 + Rerank），返回带引用信息"
        "（文档标题 / 章节 / 版本）的分块内容。"
    ),
    params_model=RagSearchParams,
)
def rag_search(params: RagSearchParams, ctx: ToolContext) -> ToolResult:
    results = search(
        params.query,
        top_k=params.top_k,
        document_type=params.document_type,
        equipment_type=params.equipment_type,
    )
    return ToolResult(
        tool="rag.search",
        data=results,
        meta={
            "source": "postgres:document_chunks",
            "row_count": len(results),
            "query": params.query,
        },
    )

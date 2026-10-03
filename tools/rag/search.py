"""混合检索：pgvector 余弦 + 关键词 ILIKE → RRF 融合 → 轻量词法 Rerank。

Rerank 说明：MVP 使用词元重叠加权的轻量策略（无需额外模型）；
后续可替换为 Cross-Encoder 重排（接口不变）。

检索 SQL 同样经 ``run_readonly_query`` 执行 —— Validator 在此路径上不可绕过。
"""

from tools.rag.embedding import get_embedding_provider, tokenize
from tools.sql.engine import run_readonly_query

VECTOR_TOP_K = 20
KEYWORD_TOP_K = 20
RRF_K = 60
_RAG_TABLES = {"document_chunks", "documents"}
_MAX_KEYWORD_TOKENS = 12
_STOP_CHARS = set("的了是在有和与或怎么吗呢哪我你他她它这那")


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _keyword_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for token in tokenize(query):
        if len(token) < 2:
            continue
        if any(char in _STOP_CHARS for char in token):
            continue
        if token not in tokens:
            tokens.append(token)
        if len(tokens) >= _MAX_KEYWORD_TOKENS:
            break
    return tokens


def _keyword_sql(tokens: list[str], filters: list[str]) -> str:
    """构造关键词臂 SQL：WHERE 决定候选，ORDER BY 决定相关度顺序。

    缺 ORDER BY 时 ``LIMIT`` 截取的是堆序行（与查询无关），会把噪声喂进 RRF 融合。
    相关度 = 命中 token 数（与 Python 端 ``_match_count`` 同序），并以 ``c.id`` 兜底
    保证结果完全确定。

    占位符顺序（参数必须按此顺序拼接）::

        WHERE token × n  →  filters × m  →  ORDER BY token × n  →  LIMIT
    """
    keyword_conditions = " OR ".join(["c.content ILIKE %s"] * len(tokens))
    relevance = " + ".join(
        ["CASE WHEN c.content ILIKE %s THEN 1 ELSE 0 END"] * len(tokens)
    )
    sql_text = (
        "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.content, c.metadata, "
        "d.title AS document_title, d.document_type, d.equipment_type, d.version "
        "FROM document_chunks c JOIN documents d ON d.document_id = c.document_id "
        f"WHERE ({keyword_conditions})"
    )
    if filters:
        sql_text += " AND " + " AND ".join(filters)
    return sql_text + f" ORDER BY ({relevance}) DESC, c.id ASC LIMIT %s"


def _keyword_params(
    tokens: list[str], filter_params: list, top_k: int
) -> tuple:
    """按 ``_keyword_sql`` 声明的占位符顺序拼接参数。"""
    patterns = [f"%{token}%" for token in tokens]
    return tuple(patterns + list(filter_params) + patterns + [top_k])


def search(
    query: str,
    top_k: int = 5,
    document_type: str | None = None,
    equipment_type: str | None = None,
) -> list[dict]:
    provider = get_embedding_provider()
    query_vector = provider.embed([query])[0]
    tokens = _keyword_tokens(query)

    base_select = (
        "SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.content, c.metadata, "
        "d.title AS document_title, d.document_type, d.equipment_type, d.version "
        "FROM document_chunks c JOIN documents d ON d.document_id = c.document_id "
    )
    filters: list[str] = []
    filter_params: list = []
    if document_type:
        filters.append("d.document_type = %s")
        filter_params.append(document_type)
    if equipment_type:
        filters.append("d.equipment_type = %s")
        filter_params.append(equipment_type)

    vector_conditions = ["c.embedding IS NOT NULL", *filters]
    vector_sql = (
        base_select
        + "WHERE "
        + " AND ".join(vector_conditions)
        + " ORDER BY c.embedding <=> %s::vector LIMIT %s"
    )
    vector_rows = run_readonly_query(
        vector_sql,
        (*filter_params, _vector_literal(query_vector), VECTOR_TOP_K),
        allowed_tables=_RAG_TABLES,
    )

    keyword_rows: list[dict] = []
    if tokens:
        keyword_sql = _keyword_sql(tokens, filters)
        keyword_rows = run_readonly_query(
            keyword_sql,
            _keyword_params(tokens, filter_params, KEYWORD_TOP_K),
            allowed_tables=_RAG_TABLES,
        )

    fused: dict[int, dict] = {}

    def _entry(row: dict) -> dict:
        return fused.setdefault(
            row["chunk_id"],
            {
                **row,
                "vector_rank": None,
                "keyword_rank": None,
                "rrf": 0.0,
            },
        )

    for rank, row in enumerate(vector_rows, start=1):
        entry = _entry(row)
        entry["vector_rank"] = rank
        entry["rrf"] += 1.0 / (RRF_K + rank)

    def _match_count(row: dict) -> int:
        content = row["content"].lower()
        return sum(1 for token in tokens if token in content)

    # keyword_rows 已按 SQL 端相关度排序（与 _match_count 同序），此处仅补空位排序兜底
    keyword_rows.sort(key=_match_count, reverse=True)
    for rank, row in enumerate(keyword_rows, start=1):
        entry = _entry(row)
        entry["keyword_rank"] = rank
        entry["rrf"] += 1.0 / (RRF_K + rank)

    for entry in fused.values():
        content_tokens = set(tokenize(entry["content"]))
        overlap = sum(1 for token in tokens if token in content_tokens)
        overlap_ratio = overlap / len(tokens) if tokens else 0.0
        entry["keyword_hits"] = overlap
        entry["rerank_score"] = round(entry["rrf"] * (1.0 + 0.15 * overlap_ratio), 6)
        entry["scores"] = {
            "vector_rank": entry["vector_rank"],
            "keyword_rank": entry["keyword_rank"],
            "keyword_hits": overlap,
            "rrf": round(entry["rrf"], 6),
            "rerank": entry["rerank_score"],
        }

    ranked = sorted(fused.values(), key=lambda item: item["rerank_score"], reverse=True)
    results: list[dict] = []
    for entry in ranked[:top_k]:
        metadata = entry.get("metadata") or {}
        results.append(
            {
                "chunk_id": entry["chunk_id"],
                "document_title": entry["document_title"],
                "document_type": entry["document_type"],
                "equipment_type": entry["equipment_type"],
                "version": entry["version"],
                "chunk_index": entry["chunk_index"],
                "section": metadata.get("section"),
                "source_file": metadata.get("source_file"),
                "content": entry["content"],
                "scores": entry["scores"],
            }
        )
    return results

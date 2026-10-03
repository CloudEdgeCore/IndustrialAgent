"""RAG retrieval indexes (pgvector HNSW + pg_trgm for keyword arm)

Revision ID: p7a1ragindex01
Revises: e12e12db2c57
Create Date: 2026-10-03

背景（P7 加固）：
- `document_chunks.embedding` 原先没有任何向量索引，余弦检索全表顺序扫描；
- 关键词臂使用 `content ILIKE '%token%'`，无 trigram 索引支撑。

说明：当前知识库规模（数十个分块）下 Postgres 仍可能选择顺序扫描 —— 索引是为
规模增长准备的正确结构，不代表小数据量下一定被命中。

"""
from typing import Sequence, Union

from alembic import op

revision: str = "p7a1ragindex01"
down_revision: Union[str, None] = "e12e12db2c57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 关键词臂的 ILIKE '%...%' 需要 trigram 索引才能走索引扫描
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm "
        "ON document_chunks USING gin (content gin_trgm_ops)"
    )
    # 向量臂：余弦距离的 HNSW 近似最近邻索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")

"""知识文档导入：解析 → 分块 → 向量化 → 写入 documents / document_chunks。"""

import json
from pathlib import Path

from tools.db import app_db_connection
from tools.rag.embedding import get_embedding_provider
from tools.rag.parser import chunk_document, parse_document

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "knowledge"


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def ingest_documents(paths: list[Path] | None = None) -> dict:
    files = sorted(paths) if paths else sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        raise ValueError(f"没有可导入的文档: {KNOWLEDGE_DIR}")

    provider = get_embedding_provider()
    documents = 0
    chunk_total = 0

    with app_db_connection() as conn:
        with conn.cursor() as cur:
            for path in files:
                doc = parse_document(path)
                chunks = chunk_document(doc)
                if not chunks:
                    continue
                embeddings = provider.embed([chunk.content for chunk in chunks])

                cur.execute("DELETE FROM documents WHERE title = %s", (doc.title,))
                cur.execute(
                    "INSERT INTO documents (title, document_type, equipment_type, "
                    "equipment_model, version, file_path, status, chunk_count) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'indexed', %s) RETURNING document_id",
                    (
                        doc.title,
                        doc.document_type,
                        doc.equipment_type,
                        doc.equipment_model,
                        doc.version,
                        doc.source_file,
                        len(chunks),
                    ),
                )
                document_id = cur.fetchone()[0]
                cur.executemany(
                    "INSERT INTO document_chunks (document_id, chunk_index, content, "
                    "embedding, metadata, token_count) "
                    "VALUES (%s, %s, %s, %s::vector, %s, %s)",
                    [
                        (
                            document_id,
                            chunk.index,
                            chunk.content,
                            _vector_literal(embedding),
                            json.dumps(
                                {
                                    "section": chunk.section,
                                    "source_file": chunk.source_file,
                                },
                                ensure_ascii=False,
                            ),
                            len(chunk.content),
                        )
                        for chunk, embedding in zip(chunks, embeddings, strict=True)
                    ],
                )
                documents += 1
                chunk_total += len(chunks)
        conn.commit()

    return {
        "documents": documents,
        "chunks": chunk_total,
        "provider": type(provider).__name__,
    }

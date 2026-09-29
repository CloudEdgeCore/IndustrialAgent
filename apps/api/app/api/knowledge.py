"""知识库 API（文档列表 + RAG 检索，只读）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DocumentOut, SearchHitOut
from models import Document
from tools.rag.search import search as rag_search

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)
    document_type: str | None = None


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    items = db.scalars(select(Document).order_by(Document.document_id)).all()
    return [DocumentOut.model_validate(item) for item in items]


@router.post("/search", response_model=list[SearchHitOut])
def knowledge_search(payload: KnowledgeSearchRequest) -> list[SearchHitOut]:
    results = rag_search(
        payload.query, top_k=payload.top_k, document_type=payload.document_type
    )
    return [SearchHitOut(**item) for item in results]

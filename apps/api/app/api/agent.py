"""Agent 对话 API：SSE 流式输出（业务步骤，不暴露思维链）+ 会话消息。"""

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.runner import run_agent_streaming
from app.api.auth import get_current_user
from app.db import get_db
from app.schemas import ChatRequest, MessageOut
from app.services.sessions import persist_agent_run
from models import AgentMessage, User

router = APIRouter(prefix="/agent", tags=["agent"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat")
def agent_chat(
    payload: ChatRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    model = getattr(request.app.state, "agent_model", None)

    def stream() -> Iterator[str]:
        yield _sse(
            {"type": "step", "label": "分析任务", "status": "started", "tool": None}
        )
        for event in run_agent_streaming(
            payload.query,
            context=payload.context,
            model=model,
            session_id=payload.session_id,
            on_complete=persist_agent_run,
        ):
            yield _sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def session_messages(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    items = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.id)
    ).all()
    return [MessageOut.model_validate(item) for item in items]

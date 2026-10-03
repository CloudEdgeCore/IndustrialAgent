"""Agent 会话持久化：sessions / messages / tasks（在 Agent 运行完成后调用）。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from agent.state import AgentState
from app.db import SessionLocal
from models import AgentMessage, AgentSession, AnalysisTask

# 注入提示词的最近消息条数（多轮上下文）
HISTORY_LIMIT = 6


def load_history(session_id: str | None, limit: int = HISTORY_LIMIT) -> list[dict]:
    """读取最近 N 条会话消息，按时间正序返回 {role, content}。

    没有历史时返回空列表 —— Agent 仍可正常工作，只是没有多轮上下文。
    """
    if not session_id:
        return []
    with SessionLocal() as db:
        rows = db.scalars(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.id.desc())
            .limit(limit)
        ).all()
    return [
        {"role": item.role, "content": item.content or ""}
        for item in reversed(rows)
    ]


def persist_agent_run(result: AgentState) -> None:
    session_id = result.get("session_id") or str(uuid4())
    query = result.get("user_query", "")
    final_answer = result.get("final_answer", "")
    report = result.get("report") or {}

    with SessionLocal() as db:
        if db.get(AgentSession, session_id) is None:
            db.add(AgentSession(session_id=session_id, title=query[:60] or "新会话"))
            db.flush()  # 确保 session 先落库（agent_messages 外键依赖）
        db.add(AgentMessage(session_id=session_id, role="user", content=query))
        db.add(
            AgentMessage(
                session_id=session_id,
                role="assistant",
                content=final_answer,
                payload={
                    "task_type": result.get("task_type"),
                    "steps": result.get("steps", []),
                    "report_id": report.get("report_id"),
                },
            )
        )
        db.add(
            AnalysisTask(
                task_id=str(uuid4()),
                session_id=session_id,
                task_type=result.get("task_type") or "unknown",
                equipment_id=(result.get("context") or {}).get("equipment_id"),
                status="completed",
                input={"query": query, "context": result.get("context") or {}},
                result={
                    "final_answer": final_answer,
                    "report_id": report.get("report_id"),
                },
                evidence={"items": result.get("evidence", [])},
                completed_at=datetime.now(UTC),
            )
        )
        db.commit()

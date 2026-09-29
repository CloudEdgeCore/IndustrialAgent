"""Agent 会话持久化：sessions / messages / tasks（在 Agent 运行完成后调用）。"""

from datetime import UTC, datetime
from uuid import uuid4

from agent.state import AgentState
from app.db import SessionLocal
from models import AgentMessage, AgentSession, AnalysisTask


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

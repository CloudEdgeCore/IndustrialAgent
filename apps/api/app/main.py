from fastapi import FastAPI

from app.api.agent import router as agent_router
from app.api.alarms import router as alarms_router
from app.api.auth import router as auth_router
from app.api.equipment import router as equipment_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.quality import router as quality_router
from app.api.reports import router as reports_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(equipment_router)
app.include_router(alarms_router)
app.include_router(quality_router)
app.include_router(knowledge_router)
app.include_router(reports_router)
app.include_router(agent_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.version, "docs": "/docs"}

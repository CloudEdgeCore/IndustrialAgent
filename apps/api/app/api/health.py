from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """存活探针：仅表示进程正常，不检查下游依赖。"""
    return {"status": "ok", "service": "api"}

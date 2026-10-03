"""元数据 API：数据新鲜度（演示/生产的"数据截至"可见性）。

为什么需要：分析窗口锚定在数据末尾时，界面必须明确告知数据的实际截止时间，
否则 3 天前的读数会被当成实时数据展示 —— 这是演示与验收中最容易误导人的地方。
"""

from fastapi import APIRouter

from tools.freshness import data_freshness

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/freshness")
def freshness() -> dict:
    """返回窗口锚点、锚点来源、数据滞后小时数与各领域最新时间。"""
    return data_freshness(force_refresh=True).to_dict()

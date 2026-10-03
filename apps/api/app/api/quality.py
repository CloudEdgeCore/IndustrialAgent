"""质量分析 API。

窗口锚点：所有相对时间窗口锚定 ``tools.freshness.data_freshness().anchor``
（默认=数据最新时间），而非 ``datetime.now()``。这样回放/模拟数据集下
"最近 N 天"始终落在数据时间轴上，不会因数据落库时间推移而静默失真；
响应同时返回 ``data_as_of`` / ``data_lag_hours``，界面可明确标注数据截止时间。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import InspectionOut, QualitySummaryOut, QualityTrendPoint
from models import QualityInspection
from tools.freshness import data_freshness

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/trend", response_model=list[QualityTrendPoint])
def quality_trend(
    product_id: str = "PRD-A",
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
) -> list[QualityTrendPoint]:
    since = data_freshness().anchor - timedelta(days=days)
    day = func.date_trunc("day", QualityInspection.inspection_time).label("day")
    rows = db.execute(
        select(
            day,
            func.count(),
            func.sum(case((QualityInspection.result == "fail", 1), else_=0)),
        )
        .where(
            QualityInspection.product_id == product_id,
            QualityInspection.inspection_time >= since,
        )
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        QualityTrendPoint(
            date=row[0].date().isoformat(),
            total=int(row[1] or 0),
            fail_count=int(row[2] or 0),
            fail_rate=round(int(row[2] or 0) / int(row[1]), 4) if row[1] else 0.0,
        )
        for row in rows
    ]


def _window_stats(
    db: Session,
    product_id: str,
    start: datetime,
    end: datetime,
    *,
    inclusive_end: bool = False,
) -> tuple[int, int]:
    upper = (
        QualityInspection.inspection_time <= end
        if inclusive_end
        else QualityInspection.inspection_time < end
    )
    row = db.execute(
        select(
            func.count(),
            func.sum(case((QualityInspection.result == "fail", 1), else_=0)),
        ).where(
            QualityInspection.product_id == product_id,
            QualityInspection.inspection_time >= start,
            upper,
        )
    ).one()
    total = int(row[0] or 0)
    fails = int(row[1] or 0)
    return total, fails


@router.get("/summary", response_model=QualitySummaryOut)
def quality_summary(
    product_id: str = "PRD-A",
    days: int = Query(3, ge=1, le=30),
    db: Session = Depends(get_db),
) -> QualitySummaryOut:
    freshness = data_freshness()
    anchor = freshness.anchor
    recent_start = anchor - timedelta(days=days)
    baseline_start = recent_start - timedelta(days=days)

    # 近期窗口闭区间（含数据末端），基线窗口左闭右开 —— 不重叠、不留缝
    total, fails = _window_stats(db, product_id, recent_start, anchor, inclusive_end=True)
    baseline_total, baseline_fails = _window_stats(
        db, product_id, baseline_start, recent_start
    )

    top_defects = db.execute(
        select(QualityInspection.defect_type, func.count().label("count"))
        .where(
            QualityInspection.product_id == product_id,
            QualityInspection.result == "fail",
            QualityInspection.inspection_time >= recent_start,
            QualityInspection.inspection_time <= anchor,
        )
        .group_by(QualityInspection.defect_type)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    by_equipment = db.execute(
        select(QualityInspection.equipment_id, func.count().label("count"))
        .where(
            QualityInspection.product_id == product_id,
            QualityInspection.result == "fail",
            QualityInspection.inspection_time >= recent_start,
            QualityInspection.inspection_time <= anchor,
        )
        .group_by(QualityInspection.equipment_id)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    return QualitySummaryOut(
        product_id=product_id,
        days=days,
        total=total,
        pass_count=total - fails,
        fail_count=fails,
        fail_rate=round(fails / total, 4) if total else 0.0,
        baseline_fail_rate=(
            round(baseline_fails / baseline_total, 4) if baseline_total else None
        ),
        top_defects=[
            {"defect_type": row.defect_type, "count": row.count} for row in top_defects
        ],
        by_equipment=[
            {"equipment_id": row.equipment_id, "count": row.count}
            for row in by_equipment
        ],
        data_as_of=anchor,
        data_lag_hours=freshness.lag_hours,
        anchor_source=freshness.resolved_from,
    )


@router.get("/inspections", response_model=list[InspectionOut])
def list_inspections(
    product_id: str | None = None,
    result: str | None = None,
    equipment_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[InspectionOut]:
    query = select(QualityInspection)
    if product_id:
        query = query.where(QualityInspection.product_id == product_id)
    if result:
        query = query.where(QualityInspection.result == result)
    if equipment_id:
        query = query.where(QualityInspection.equipment_id == equipment_id)
    items = db.scalars(
        query.order_by(QualityInspection.inspection_time.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [InspectionOut.model_validate(item) for item in items]

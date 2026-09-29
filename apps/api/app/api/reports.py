"""报告中心 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ReportDetailOut, ReportListOut, ReportOut
from models import Report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ReportListOut)
def list_reports(
    report_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ReportListOut:
    query = select(Report)
    if report_type:
        query = query.where(Report.report_type == report_type)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Report.report_id.desc()).limit(limit).offset(offset)
    ).all()
    return ReportListOut(total=total, items=[ReportOut.model_validate(i) for i in items])


@router.get("/{report_id}", response_model=ReportDetailOut)
def report_detail(report_id: int, db: Session = Depends(get_db)) -> ReportDetailOut:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"报告不存在: {report_id}")
    return ReportDetailOut.model_validate(report)

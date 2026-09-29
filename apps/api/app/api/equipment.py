"""设备中心 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AlarmOut, EquipmentDetailOut, EquipmentListOut
from models import Alarm, Equipment

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("", response_model=EquipmentListOut)
def list_equipment(
    equipment_type: str | None = None,
    status: str | None = None,
    production_line: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> EquipmentListOut:
    query = select(Equipment)
    if equipment_type:
        query = query.where(Equipment.equipment_type == equipment_type)
    if status:
        query = query.where(Equipment.status == status)
    if production_line:
        query = query.where(Equipment.production_line == production_line)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Equipment.equipment_id).limit(limit).offset(offset)
    ).all()
    return EquipmentListOut(total=total, items=items)


@router.get("/{equipment_id}", response_model=EquipmentDetailOut)
def equipment_detail(
    equipment_id: str, db: Session = Depends(get_db)
) -> EquipmentDetailOut:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail=f"设备不存在: {equipment_id}")

    alarms = db.scalars(
        select(Alarm)
        .where(Alarm.equipment_id == equipment_id, Alarm.status == "active")
        .order_by(Alarm.occurred_at.desc())
        .limit(10)
    ).all()

    rows = db.execute(
        text(
            "SELECT DISTINCT ON (sensor_type) sensor_type, value "
            "FROM sensor_readings WHERE equipment_id = :eq "
            "ORDER BY sensor_type, timestamp DESC"
        ),
        {"eq": equipment_id},
    ).all()
    latest = {row.sensor_type: float(row.value) for row in rows}

    detail = EquipmentDetailOut.model_validate(equipment)
    detail.active_alarms = [AlarmOut.model_validate(item) for item in alarms]
    detail.latest_readings = latest
    return detail

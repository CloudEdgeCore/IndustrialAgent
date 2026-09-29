"""报警查询 API。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AlarmWithEquipmentOut
from models import Alarm, Equipment

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("", response_model=list[AlarmWithEquipmentOut])
def list_alarms(
    status: str | None = None,
    equipment_id: str | None = None,
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[AlarmWithEquipmentOut]:
    query = select(Alarm, Equipment.name).join(
        Equipment, Alarm.equipment_id == Equipment.equipment_id
    )
    if status:
        query = query.where(Alarm.status == status)
    if equipment_id:
        query = query.where(Alarm.equipment_id == equipment_id)
    if severity:
        query = query.where(Alarm.severity == severity)
    rows = db.execute(
        query.order_by(Alarm.occurred_at.desc()).limit(limit).offset(offset)
    ).all()
    return [
        AlarmWithEquipmentOut.model_validate(
            {**alarm.__dict__, "equipment_name": name}
        )
        for alarm, name in rows
    ]

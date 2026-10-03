"""设备中心 API。"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    AlarmOut,
    EquipmentDetailOut,
    EquipmentListOut,
    MaintenanceOut,
    SensorPointOut,
)
from models import Alarm, Equipment, MaintenanceRecord
from tools.freshness import data_freshness

router = APIRouter(prefix="/equipment", tags=["equipment"])

_BUCKETS = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
}
_SENSOR_TYPES = ("temperature", "pressure", "speed", "vibration", "current", "flow")


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
            "SELECT DISTINCT ON (sensor_type) sensor_type, value, timestamp "
            "FROM sensor_readings WHERE equipment_id = :eq "
            "ORDER BY sensor_type, timestamp DESC"
        ),
        {"eq": equipment_id},
    ).all()
    latest = {row.sensor_type: float(row.value) for row in rows}
    latest_at = max((row.timestamp for row in rows), default=None)

    freshness = data_freshness()
    detail = EquipmentDetailOut.model_validate(equipment)
    detail.active_alarms = [AlarmOut.model_validate(item) for item in alarms]
    detail.latest_readings = latest
    detail.latest_reading_at = latest_at
    detail.data_as_of = freshness.anchor
    detail.data_lag_hours = freshness.lag_hours
    return detail


@router.get("/{equipment_id}/readings", response_model=list[SensorPointOut])
def equipment_readings(
    equipment_id: str,
    sensor_type: str = "temperature",
    hours: int = Query(24, ge=1, le=168),
    bucket: str = "5m",
    db: Session = Depends(get_db),
) -> list[SensorPointOut]:
    if db.get(Equipment, equipment_id) is None:
        raise HTTPException(status_code=404, detail=f"设备不存在: {equipment_id}")
    if sensor_type not in _SENSOR_TYPES:
        raise HTTPException(status_code=422, detail=f"非法传感器类型: {sensor_type}")
    bucket_sql = _BUCKETS.get(bucket)
    if bucket_sql is None:
        raise HTTPException(status_code=422, detail=f"非法聚合粒度: {bucket}")

    # 窗口锚定数据末尾（而非 now()），否则数据落库数天后曲线会整段变空
    anchor = data_freshness().anchor
    since = anchor - timedelta(hours=hours)
    rows = db.execute(
        text(
            "SELECT time_bucket(CAST(:bucket AS interval), timestamp) AS ts, "
            "avg(value) AS value, 'good' AS quality "
            "FROM sensor_readings WHERE equipment_id = :eq AND sensor_type = :st "
            "AND timestamp >= :since AND timestamp <= :anchor "
            "GROUP BY ts ORDER BY ts"
        ),
        {
            "bucket": bucket_sql,
            "eq": equipment_id,
            "st": sensor_type,
            "since": since,
            "anchor": anchor,
        },
    ).all()
    return [
        SensorPointOut(timestamp=row.ts, value=round(float(row.value), 3), quality=row.quality)
        for row in rows
    ]


@router.get("/{equipment_id}/maintenance", response_model=list[MaintenanceOut])
def equipment_maintenance(
    equipment_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[MaintenanceOut]:
    if db.get(Equipment, equipment_id) is None:
        raise HTTPException(status_code=404, detail=f"设备不存在: {equipment_id}")
    items = db.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.equipment_id == equipment_id)
        .order_by(MaintenanceRecord.occurred_at.desc())
        .limit(limit)
    ).all()
    return [MaintenanceOut.model_validate(item) for item in items]

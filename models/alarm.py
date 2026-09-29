from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Alarm(Base, TimestampMixin):
    """报警事件。alarm_code 对应报警代码库（alarm_catalog）。"""

    __tablename__ = "alarms"
    __table_args__ = (Index("ix_alarms_equipment_time", "equipment_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alarm_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.equipment_id"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)


class MaintenanceRecord(Base, TimestampMixin):
    """维修记录（含历史故障案例，供 History Case Tool 使用）。"""

    __tablename__ = "maintenance_records"
    __table_args__ = (
        Index("ix_maintenance_equipment_time", "equipment_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.equipment_id"), nullable=False
    )
    maintenance_type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text)
    actions: Mapped[str | None] = mapped_column(Text)
    technician: Mapped[str | None] = mapped_column(String(64))
    related_alarm_code: Mapped[str | None] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

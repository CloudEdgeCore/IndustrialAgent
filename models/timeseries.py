from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class SensorReading(Base):
    """设备时序数据（长表模型，TimescaleDB hypertable）。

    架构红线：统一长表 (timestamp / equipment_id / sensor_type / value / quality)，
    不设计宽表旁路。主键顺序 (equipment_id, sensor_type, timestamp) 以优化
    "单设备单指标时间序列" 的典型查询。
    """

    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_sensor_time", "sensor_type", "timestamp"),
    )

    equipment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sensor_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="good")


class ProcessParameter(Base):
    """产线工艺参数时序（TimescaleDB hypertable）。"""

    __tablename__ = "process_parameters"

    line_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    parameter_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="good")

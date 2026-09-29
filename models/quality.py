from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Defect(Base, TimestampMixin):
    """缺陷字典表。"""

    __tablename__ = "defects"

    defect_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)


class ProductBatch(Base, TimestampMixin):
    """生产批次。batch_id 使用可读编码（如 B20260928001）。"""

    __tablename__ = "product_batches"
    __table_args__ = (Index("ix_batches_product_time", "product_id", "started_at"),)

    batch_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(32), nullable=False)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.equipment_id"), nullable=False
    )
    production_line: Mapped[str] = mapped_column(String(32), nullable=False)
    shift: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)


class QualityInspection(Base, TimestampMixin):
    """质量检测记录（逐件检测）。"""

    __tablename__ = "quality_inspections"
    __table_args__ = (
        Index("ix_inspections_product_time", "product_id", "inspection_time"),
        Index("ix_inspections_equipment_time", "equipment_id", "inspection_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("product_batches.batch_id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(String(32), nullable=False)
    equipment_id: Mapped[str] = mapped_column(
        ForeignKey("equipment.equipment_id"), nullable=False
    )
    shift: Mapped[str] = mapped_column(String(16), nullable=False)
    inspection_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[str] = mapped_column(String(8), nullable=False)
    defect_type: Mapped[str | None] = mapped_column(
        ForeignKey("defects.defect_code"), nullable=True
    )
    process_temperature: Mapped[float | None] = mapped_column(Float)
    process_pressure: Mapped[float | None] = mapped_column(Float)

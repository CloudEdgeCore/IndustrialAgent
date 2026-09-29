from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Equipment(Base, TimestampMixin):
    """设备主数据。equipment_id 使用可读编码（如 EQ-003），便于演示与检索。"""

    __tablename__ = "equipment"

    equipment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(64))
    production_line: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    commissioned_at: Mapped[date | None] = mapped_column(Date)

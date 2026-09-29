"""API 响应模型（Pydantic）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EquipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    equipment_id: str
    name: str
    equipment_type: str
    model: str | None = None
    production_line: str
    status: str
    health_score: int


class EquipmentListOut(BaseModel):
    total: int
    items: list[EquipmentOut]


class AlarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alarm_code: str
    equipment_id: str
    severity: str
    status: str
    occurred_at: datetime
    cleared_at: datetime | None = None
    description: str | None = None


class SensorPointOut(BaseModel):
    timestamp: datetime
    value: float
    quality: str


class EquipmentDetailOut(EquipmentOut):
    active_alarms: list[AlarmOut] = Field(default_factory=list)
    latest_readings: dict[str, float] = Field(default_factory=dict)


class QualitySummaryOut(BaseModel):
    product_id: str
    days: int
    total: int
    pass_count: int
    fail_count: int
    fail_rate: float
    baseline_fail_rate: float | None = None
    top_defects: list[dict[str, Any]] = Field(default_factory=list)
    by_equipment: list[dict[str, Any]] = Field(default_factory=list)


class InspectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: str
    product_id: str
    equipment_id: str
    shift: str
    inspection_time: datetime
    result: str
    defect_type: str | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    title: str
    document_type: str
    equipment_type: str | None = None
    version: str | None = None
    status: str
    chunk_count: int


class SearchHitOut(BaseModel):
    document_title: str
    document_type: str
    version: str | None = None
    chunk_index: int
    section: str | None = None
    content: str
    scores: dict[str, Any]


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    report_type: str
    title: str
    equipment_id: str | None = None
    risk_level: str | None = None
    status: str
    created_at: datetime


class ReportListOut(BaseModel):
    total: int
    items: list[ReportOut]


class ReportDetailOut(ReportOut):
    content_markdown: str | None = None


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str | None = None
    created_at: datetime

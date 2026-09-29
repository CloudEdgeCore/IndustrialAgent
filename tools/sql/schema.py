"""SQL Tool 数据集白名单：只允许查询登记在册的表与列。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    table: str
    time_field: str
    columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    default_order_field: str
    default_order_desc: bool = True


DATASETS: dict[str, DatasetSpec] = {
    "equipment": DatasetSpec(
        table="equipment",
        time_field="created_at",
        columns=(
            "equipment_id",
            "name",
            "equipment_type",
            "model",
            "production_line",
            "status",
            "health_score",
            "commissioned_at",
            "created_at",
            "updated_at",
        ),
        numeric_columns=("health_score",),
        default_order_field="equipment_id",
        default_order_desc=False,
    ),
    "alarms": DatasetSpec(
        table="alarms",
        time_field="occurred_at",
        columns=(
            "id",
            "alarm_code",
            "equipment_id",
            "severity",
            "status",
            "occurred_at",
            "cleared_at",
            "description",
        ),
        numeric_columns=("id",),
        default_order_field="occurred_at",
    ),
    "maintenance_records": DatasetSpec(
        table="maintenance_records",
        time_field="occurred_at",
        columns=(
            "id",
            "equipment_id",
            "maintenance_type",
            "description",
            "root_cause",
            "actions",
            "technician",
            "related_alarm_code",
            "occurred_at",
            "completed_at",
        ),
        numeric_columns=("id",),
        default_order_field="occurred_at",
    ),
    "product_batches": DatasetSpec(
        table="product_batches",
        time_field="started_at",
        columns=(
            "batch_id",
            "product_id",
            "equipment_id",
            "production_line",
            "shift",
            "started_at",
            "finished_at",
            "quantity",
        ),
        numeric_columns=("quantity",),
        default_order_field="started_at",
    ),
    "quality_inspections": DatasetSpec(
        table="quality_inspections",
        time_field="inspection_time",
        columns=(
            "id",
            "batch_id",
            "product_id",
            "equipment_id",
            "shift",
            "inspection_time",
            "result",
            "defect_type",
            "process_temperature",
            "process_pressure",
        ),
        numeric_columns=("id", "process_temperature", "process_pressure"),
        default_order_field="inspection_time",
    ),
    "defects": DatasetSpec(
        table="defects",
        time_field="created_at",
        columns=("defect_code", "name", "category", "description"),
        numeric_columns=(),
        default_order_field="defect_code",
        default_order_desc=False,
    ),
}

ALLOWED_TABLES: set[str] = {spec.table for spec in DATASETS.values()}

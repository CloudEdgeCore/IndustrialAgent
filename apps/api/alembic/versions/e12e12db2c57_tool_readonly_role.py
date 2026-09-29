"""tool readonly role

Revision ID: e12e12db2c57
Revises: fc15b2062d40
Create Date: 2026-09-29 21:07:11.064199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e12e12db2c57'
down_revision: Union[str, None] = 'fc15b2062d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOOL_RO_TABLES = [
    "equipment",
    "alarms",
    "maintenance_records",
    "product_batches",
    "quality_inspections",
    "defects",
    "documents",
    "document_chunks",
    "sensor_readings",
    "process_parameters",
]


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tool_ro') THEN
                CREATE ROLE tool_ro LOGIN PASSWORD 'tool_ro';
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO tool_ro")
    op.execute(f"GRANT SELECT ON {', '.join(TOOL_RO_TABLES)} TO tool_ro")
    op.execute("ALTER ROLE tool_ro SET default_transaction_read_only = on")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT ON {', '.join(TOOL_RO_TABLES)} FROM tool_ro")
    op.execute("REVOKE USAGE ON SCHEMA public FROM tool_ro")
    op.execute("DROP ROLE IF EXISTS tool_ro")

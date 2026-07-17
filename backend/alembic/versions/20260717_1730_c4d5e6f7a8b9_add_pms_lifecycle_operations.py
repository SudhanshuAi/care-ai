"""record each appointment lifecycle operation in mock PMS

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-07-17 17:30:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS "
        "pms_sync_operation VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE mock_pms_appointments ADD COLUMN IF NOT EXISTS "
        "operation VARCHAR(32) NOT NULL DEFAULT 'create'"
    )
    # Existing receipts represent initial booking write-backs. Multiple
    # lifecycle events for one appointment now need their own receipts.
    op.execute(
        "ALTER TABLE mock_pms_appointments DROP CONSTRAINT IF EXISTS "
        "mock_pms_appointments_appointment_id_key"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM mock_pms_appointments newer USING mock_pms_appointments older "
        "WHERE newer.appointment_id = older.appointment_id "
        "AND newer.received_at > older.received_at"
    )
    op.create_unique_constraint(
        "mock_pms_appointments_appointment_id_key",
        "mock_pms_appointments",
        ["appointment_id"],
    )
    op.drop_column("mock_pms_appointments", "operation")
    op.drop_column("appointments", "pms_sync_operation")

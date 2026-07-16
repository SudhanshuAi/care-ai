"""add durable mock PMS sync state

Revision ID: a9b3c4d5e6f7
Revises: f8a2b3c4d5e6
Create Date: 2026-07-16 19:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9b3c4d5e6f7"
down_revision: Union[str, None] = "f8a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `IF NOT EXISTS` safely handles databases where these operational
    # columns were added manually before this revision was introduced.
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS "
        "pms_sync_attempts INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS "
        "pms_last_attempt_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS "
        "pms_synced_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS pms_last_error TEXT"
    )
    op.create_table(
        "mock_pms_appointments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_mock_pms_appointments_appointment_id",
        "mock_pms_appointments",
        ["appointment_id"],
        unique=False,
    )
    op.create_index(
        "ix_mock_pms_appointments_idempotency_key",
        "mock_pms_appointments",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mock_pms_appointments_idempotency_key",
        table_name="mock_pms_appointments",
    )
    op.drop_index(
        "ix_mock_pms_appointments_appointment_id",
        table_name="mock_pms_appointments",
    )
    op.drop_table("mock_pms_appointments")
    op.drop_column("appointments", "pms_last_error")
    op.drop_column("appointments", "pms_synced_at")
    op.drop_column("appointments", "pms_last_attempt_at")
    op.drop_column("appointments", "pms_sync_attempts")

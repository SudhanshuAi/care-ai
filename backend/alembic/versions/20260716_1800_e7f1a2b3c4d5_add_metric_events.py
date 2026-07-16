"""add metric events

Revision ID: e7f1a2b3c4d5
Revises: c5662290beb3
Create Date: 2026-07-16 18:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f1a2b3c4d5"
down_revision: Union[str, None] = "c5662290beb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metric_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("call_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_events_name", "metric_events", ["name"], unique=False)
    op.create_index(
        "ix_metric_events_call_id", "metric_events", ["call_id"], unique=False
    )
    op.create_index(
        "ix_metric_events_occurred_at", "metric_events", ["occurred_at"], unique=False
    )
    op.create_index(
        "ix_metric_events_name_occurred_at",
        "metric_events",
        ["name", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_metric_events_name_occurred_at", table_name="metric_events")
    op.drop_index("ix_metric_events_occurred_at", table_name="metric_events")
    op.drop_index("ix_metric_events_call_id", table_name="metric_events")
    op.drop_index("ix_metric_events_name", table_name="metric_events")
    op.drop_table("metric_events")

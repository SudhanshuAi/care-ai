"""add availability offers for booking guardrails

Revision ID: f8a2b3c4d5e6
Revises: e7f1a2b3c4d5
Create Date: 2026-07-16 18:30:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a2b3c4d5e6"
down_revision: Union[str, None] = "e7f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "availability_offers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("practitioner_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("appointment_type_id", sa.UUID(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_appointment_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id"],
            ["appointment_types.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_appointment_id"],
            ["appointments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["practitioner_id"],
            ["practitioners.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_offers_expires_at",
        "availability_offers",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_availability_offers_slot_lookup",
        "availability_offers",
        ["practitioner_id", "branch_id", "appointment_type_id", "start_time"],
        unique=False,
    )
    op.create_index(
        "uq_followups_open_call_category",
        "followups",
        ["call_id", "category"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_followups_open_call_category",
        table_name="followups",
    )
    op.drop_index(
        "ix_availability_offers_slot_lookup", table_name="availability_offers"
    )
    op.drop_index(
        "ix_availability_offers_expires_at", table_name="availability_offers"
    )
    op.drop_table("availability_offers")

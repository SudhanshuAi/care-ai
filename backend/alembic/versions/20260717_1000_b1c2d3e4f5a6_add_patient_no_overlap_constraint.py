"""add patient-scoped no-overlap exclusion constraint

Revision ID: b1c2d3e4f5a6
Revises: a9b3c4d5e6f7
Create Date: 2026-07-17 10:00:00.000000+00:00

The existing `uq_appointment_no_overlap` EXCLUDE constraint only stops
two BOOKED appointments from overlapping for the *same practitioner*.
Nothing at the DB layer previously stopped the same patient from being
booked into two overlapping appointments with two different
practitioners/branches -- a real source of "duplicate" appointments
for a patient. This adds the mirror constraint scoped to `patient_id`.

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `btree_gist` was already enabled by the initial migration for the
    # practitioner-scoped constraint; safe to no-op if already present.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE appointments "
        "ADD CONSTRAINT uq_appointment_patient_no_overlap "
        "EXCLUDE USING gist ("
        "  patient_id WITH =, "
        "  tstzrange(start_time, end_time, '[)') WITH && "
        ") WHERE (status = 'booked')"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appointments DROP CONSTRAINT uq_appointment_patient_no_overlap"
    )

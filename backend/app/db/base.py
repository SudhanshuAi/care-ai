"""Declarative base for all ORM models.

Kept in its own module (rather than in `session.py`) so that Alembic's
`env.py` can import `Base.metadata` without also importing the engine /
session machinery, and so that future model modules only need to depend
on this file, not on how the database connection is configured.

No models are defined here yet -- this is infrastructure only. Models
land in `app/db/models/` in a later milestone.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class every ORM model in the project inherits from."""

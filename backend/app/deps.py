"""Central place to import FastAPI dependencies from.

Routers should depend on the names re-exported here (`get_db`,
`get_settings`) rather than reaching into `app.db.session` or
`app.core.config` directly. This gives us one seam to change how a
dependency is constructed (e.g. swap in a test session, add caching)
without touching every router.
"""

from app.core.config import Settings, get_settings
from app.db.session import get_db

__all__ = ["get_db", "get_settings", "Settings"]

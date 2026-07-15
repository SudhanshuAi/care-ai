"""Health check endpoints.

Two distinct probes, deliberately kept separate:

  * `GET /health/live`  -- liveness: is the process up at all? Never
    touches the database. Used by an orchestrator to decide whether to
    restart the container.
  * `GET /health/ready` -- readiness: can this instance actually serve
    traffic right now (i.e. can it reach Postgres)? Used to decide
    whether to route traffic to it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

"""Liveness and database-connectivity checks.

These endpoints are unauthenticated by design (no users exist before
Phase 1 auth lands) and return no data beyond a status flag. Errors are
logged server-side only — never echoed to the client, since driver
errors can contain host/user details.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/db")
async def health_db(db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="database unreachable") from None
    return {"status": "ok", "database": "reachable"}

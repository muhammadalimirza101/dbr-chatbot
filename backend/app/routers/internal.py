"""Internal endpoints for the connector (shared-secret protected).

- media bytes by id, so the connector can send images/PDFs without ever
  handling file paths
- WhatsApp auth-state storage (Baileys session in Postgres), so the
  connector survives restarts/redeploys without re-pairing. The connector
  itself never touches the database — it goes through these endpoints.
"""

import hmac
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.dependencies import DbSession
from app.models import MediaAsset, WAAuthState

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_secret(provided: str | None) -> None:
    expected = get_settings().connector_shared_secret
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


def _resolve_media_path(filename: str) -> Path | None:
    """filename is server-generated; resolve + containment check anyway."""
    storage = Path(get_settings().media_storage_dir).resolve()
    path = (storage / filename).resolve()
    if not path.is_relative_to(storage) or not path.is_file():
        return None
    return path


@router.get("/media/{media_id}")
async def get_media(
    media_id: int,
    db: DbSession,
    x_connector_secret: str | None = Header(default=None),
) -> FileResponse:
    _check_secret(x_connector_secret)
    asset = await db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    path = _resolve_media_path(asset.filename)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return FileResponse(path, media_type=asset.mime_type)


# --- WhatsApp auth state (Baileys session in Postgres) -------------------

_MAX_KEYS_PER_CALL = 500
_MAX_VALUE_CHARS = 1_000_000  # creds are a few KB; generous ceiling


class WAAuthGet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keys: list[str] = Field(min_length=1, max_length=_MAX_KEYS_PER_CALL)


class WAAuthSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # value None = delete that key
    values: dict[str, str | None] = Field(min_length=1)

    def model_post_init(self, __context: object) -> None:
        if len(self.values) > _MAX_KEYS_PER_CALL:
            raise ValueError("too many keys")
        for key, value in self.values.items():
            if not key or len(key) > 128:
                raise ValueError("invalid key")
            if value is not None and len(value) > _MAX_VALUE_CHARS:
                raise ValueError("value too large")


@router.post("/wa-auth/get")
async def wa_auth_get(
    body: WAAuthGet,
    db: DbSession,
    x_connector_secret: str | None = Header(default=None),
) -> dict[str, dict[str, str | None]]:
    _check_secret(x_connector_secret)
    rows = (
        await db.execute(
            select(WAAuthState).where(WAAuthState.key.in_(body.keys[:_MAX_KEYS_PER_CALL]))
        )
    ).scalars()
    found = {row.key: row.value for row in rows}
    return {"values": {key: found.get(key) for key in body.keys}}


@router.post("/wa-auth/set")
async def wa_auth_set(
    body: WAAuthSet,
    db: DbSession,
    x_connector_secret: str | None = Header(default=None),
) -> dict[str, str]:
    _check_secret(x_connector_secret)
    to_delete = [key for key, value in body.values.items() if value is None]
    to_upsert = [
        {"key": key, "value": value}
        for key, value in body.values.items()
        if value is not None
    ]
    if to_delete:
        await db.execute(delete(WAAuthState).where(WAAuthState.key.in_(to_delete)))
    if to_upsert:
        statement = pg_insert(WAAuthState).values(to_upsert)
        statement = statement.on_conflict_do_update(
            index_elements=[WAAuthState.key],
            set_={"value": statement.excluded.value},
        )
        await db.execute(statement)
    await db.commit()
    return {"status": "ok"}


@router.post("/wa-auth/clear")
async def wa_auth_clear(
    db: DbSession,
    x_connector_secret: str | None = Header(default=None),
) -> dict[str, str | int]:
    """Wipe the stored session — used when switching to a new number."""
    _check_secret(x_connector_secret)
    result = await db.execute(delete(WAAuthState))
    await db.commit()
    return {"status": "cleared", "deleted": result.rowcount}

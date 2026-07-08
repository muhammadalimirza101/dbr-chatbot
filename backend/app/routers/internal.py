"""Internal endpoints for the connector (shared-secret protected).

Currently: media bytes by id, so the connector can send images/PDFs
without ever handling file paths.
"""

import hmac
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.config import get_settings
from app.dependencies import DbSession
from app.models import MediaAsset

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

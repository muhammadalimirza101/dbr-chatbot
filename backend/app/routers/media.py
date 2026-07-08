"""Media asset library (room photos, rate card PDF, location pin assets).

Upload is admin-only with server-side MIME whitelist + magic-byte sniffing
+ size cap. Files are stored outside any webroot under server-generated
uuid names; user-supplied filenames are metadata only, never paths.
"""

import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import get_settings
from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models import MediaAsset
from app.models.enums import MediaPurpose
from app.schemas.dashboard import MediaOut
from app.services.audit import record_audit

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# whitelist: declared MIME -> (extension, magic-byte prefixes)
_ALLOWED: dict[str, tuple[str, list[bytes]]] = {
    "image/jpeg": (".jpg", [b"\xff\xd8\xff"]),
    "image/png": (".png", [b"\x89PNG\r\n\x1a\n"]),
    "image/webp": (".webp", [b"RIFF"]),
    "application/pdf": (".pdf", [b"%PDF"]),
}


def _storage_dir() -> Path:
    directory = Path(get_settings().media_storage_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@router.get("", response_model=list[MediaOut])
async def list_media(user: CurrentUser, db: DbSession) -> list[MediaOut]:
    assets = (
        (await db.execute(select(MediaAsset).order_by(MediaAsset.id.desc())))
        .scalars()
        .all()
    )
    return [MediaOut.model_validate(a) for a in assets]


@router.post("", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile, purpose: MediaPurpose, admin: AdminUser, db: DbSession
) -> MediaOut:
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in _ALLOWED:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "only JPEG, PNG, WebP images and PDF are allowed",
        )
    extension, magics = _ALLOWED[declared]

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file exceeds 10 MB")
    if not any(data.startswith(m) for m in magics):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "file content does not match its type"
        )

    filename = f"{uuid.uuid4().hex}{extension}"  # server-generated, never user input
    path = _storage_dir() / filename
    await anyio.Path(path).write_bytes(data)

    asset = MediaAsset(
        filename=filename,
        original_name=(file.filename or "upload")[:255],
        mime_type=declared,
        size_bytes=len(data),
        purpose=purpose,
        uploaded_by=admin.id,
    )
    db.add(asset)
    await db.flush()
    await record_audit(
        db, user_id=admin.id, action="media_uploaded", entity_type="media_asset",
        entity_id=asset.id, details={"purpose": purpose.value, "mime": declared},
    )
    await db.commit()
    await db.refresh(asset)
    return MediaOut.model_validate(asset)


@router.get("/{media_id}/file")
async def get_media_file(
    media_id: int, user: CurrentUser, db: DbSession
) -> FileResponse:
    asset = await db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    storage = _storage_dir()
    path = (storage / asset.filename).resolve()
    if not path.is_relative_to(storage) or not await anyio.Path(path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return FileResponse(path, media_type=asset.mime_type)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(media_id: int, admin: AdminUser, db: DbSession) -> None:
    asset = await db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    storage = _storage_dir()
    path = (storage / asset.filename).resolve()
    await record_audit(
        db, user_id=admin.id, action="media_deleted", entity_type="media_asset",
        entity_id=asset.id, details={"purpose": asset.purpose.value},
    )
    await db.delete(asset)
    await db.commit()
    if path.is_relative_to(storage):
        file = anyio.Path(path)
        if await file.is_file():
            await file.unlink()

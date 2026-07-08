"""Knowledge base CRUD — admin only.

Embeddings are generated server-side on create/update (no manual
"vectorize" step) and the in-memory cache is refreshed after every
mutation. Every change is audit-logged.
"""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models import KnowledgeBase
from app.schemas.kb import KBCreate, KBOut, KBUpdate
from app.services.audit import record_audit
from app.services.embeddings import embed_text, embedding_cache

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


def _to_out(entry: KnowledgeBase) -> KBOut:
    out = KBOut.model_validate(entry)
    out.has_embedding = entry.embedding is not None
    return out


async def _get_or_404(db: DbSession, kb_id: int) -> KnowledgeBase:
    entry = await db.get(KnowledgeBase, kb_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KB entry not found")
    return entry


@router.get("", response_model=list[KBOut])
async def list_entries(
    admin: AdminUser,
    db: DbSession,
    category: str | None = Query(default=None, max_length=50),
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[KBOut]:
    query = select(KnowledgeBase).order_by(KnowledgeBase.id).limit(limit).offset(offset)
    if category is not None:
        query = query.where(KnowledgeBase.category == category)
    if not include_inactive:
        query = query.where(KnowledgeBase.is_active.is_(True))
    entries = (await db.execute(query)).scalars().all()
    return [_to_out(e) for e in entries]


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
async def create_entry(body: KBCreate, admin: AdminUser, db: DbSession) -> KBOut:
    entry = KnowledgeBase(
        question=body.question,
        answer=body.answer,
        category=body.category,
        embedding=await embed_text(body.question),
        created_by=admin.id,
    )
    db.add(entry)
    await db.flush()
    await record_audit(
        db, user_id=admin.id, action="kb_create", entity_type="knowledge_base",
        entity_id=entry.id, details={"category": body.category},
    )
    await db.commit()
    await db.refresh(entry)
    await embedding_cache.refresh(db)
    return _to_out(entry)


@router.put("/{kb_id}", response_model=KBOut)
async def update_entry(
    kb_id: int, body: KBUpdate, admin: AdminUser, db: DbSession
) -> KBOut:
    entry = await _get_or_404(db, kb_id)
    changed_fields = body.model_dump(exclude_unset=True)
    if not changed_fields:
        return _to_out(entry)

    for field, value in changed_fields.items():
        setattr(entry, field, value)
    # question is what gets matched against incoming messages — re-embed on change
    if "question" in changed_fields:
        entry.embedding = await embed_text(entry.question)

    await record_audit(
        db, user_id=admin.id, action="kb_update", entity_type="knowledge_base",
        entity_id=entry.id, details={"fields": sorted(changed_fields)},
    )
    await db.commit()
    await db.refresh(entry)
    await embedding_cache.refresh(db)
    return _to_out(entry)


@router.patch("/{kb_id}/toggle", response_model=KBOut)
async def toggle_entry(kb_id: int, admin: AdminUser, db: DbSession) -> KBOut:
    entry = await _get_or_404(db, kb_id)
    entry.is_active = not entry.is_active
    await record_audit(
        db, user_id=admin.id, action="kb_toggle", entity_type="knowledge_base",
        entity_id=entry.id, details={"is_active": entry.is_active},
    )
    await db.commit()
    await db.refresh(entry)
    await embedding_cache.refresh(db)
    return _to_out(entry)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(kb_id: int, admin: AdminUser, db: DbSession) -> None:
    entry = await _get_or_404(db, kb_id)
    await record_audit(
        db, user_id=admin.id, action="kb_delete", entity_type="knowledge_base",
        entity_id=entry.id, details={"category": entry.category},
    )
    await db.delete(entry)
    await db.commit()
    await embedding_cache.refresh(db)

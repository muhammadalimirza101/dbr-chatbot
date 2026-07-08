"""Unanswered-questions queue — admin only.

One-click convert-to-KB: creates the entry (embedding generated
server-side), marks the question resolved, refreshes the cache.
Registered BEFORE the /kb/{kb_id} routes so the path never collides.
"""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.models import KnowledgeBase, UnansweredQuestion
from app.schemas.dashboard import ConvertToKB, UnansweredOut
from app.schemas.kb import KBOut
from app.services.audit import record_audit
from app.services.embeddings import embed_text, embedding_cache

router = APIRouter(prefix="/kb/unanswered", tags=["knowledge-base"])


@router.get("", response_model=list[UnansweredOut])
async def list_unanswered(
    admin: AdminUser,
    db: DbSession,
    resolved: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[UnansweredOut]:
    rows = (
        (
            await db.execute(
                select(UnansweredQuestion)
                .where(UnansweredQuestion.resolved == resolved)
                .order_by(UnansweredQuestion.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [UnansweredOut.model_validate(r) for r in rows]


async def _get_or_404(db: DbSession, question_id: int) -> UnansweredQuestion:
    row = await db.get(UnansweredQuestion, question_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return row


@router.post("/{question_id}/resolve", response_model=UnansweredOut)
async def resolve_question(
    question_id: int, admin: AdminUser, db: DbSession
) -> UnansweredOut:
    row = await _get_or_404(db, question_id)
    row.resolved = True
    await record_audit(
        db, user_id=admin.id, action="unanswered_resolved",
        entity_type="unanswered_question", entity_id=row.id,
    )
    await db.commit()
    await db.refresh(row)
    return UnansweredOut.model_validate(row)


@router.post("/{question_id}/convert", response_model=KBOut, status_code=201)
async def convert_to_kb(
    question_id: int, body: ConvertToKB, admin: AdminUser, db: DbSession
) -> KBOut:
    row = await _get_or_404(db, question_id)
    question = body.question or row.question_text
    entry = KnowledgeBase(
        question=question,
        answer=body.answer,
        category=body.category,
        embedding=await embed_text(question),
        created_by=admin.id,
    )
    db.add(entry)
    row.resolved = True
    await db.flush()
    await record_audit(
        db, user_id=admin.id, action="unanswered_converted_to_kb",
        entity_type="knowledge_base", entity_id=entry.id,
        details={"unanswered_id": row.id},
    )
    await db.commit()
    await db.refresh(entry)
    await embedding_cache.refresh(db)
    out = KBOut.model_validate(entry)
    out.has_embedding = True
    return out

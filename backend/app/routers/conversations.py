"""Live conversations: inbox, thread, takeover/return, agent replies,
and the dashboard websocket. Available to agents and admins.
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Query, WebSocket, status
from sqlalchemy import Select, or_, select

from app.database import async_session_factory
from app.dependencies import CurrentUser, DbSession
from app.models import Conversation, Customer, Message, User
from app.models.enums import (
    ContentType,
    ConversationStatus,
    MessageDirection,
    SenderType,
)
from app.schemas.dashboard import AgentReply, ConversationListItem, MessageOut
from app.services import connector
from app.services.audit import record_audit
from app.services.auth import decode_token
from app.services.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _base_query() -> Select:
    return (
        select(Conversation, Customer.phone, Customer.name)
        .join(Customer, Conversation.customer_id == Customer.id)
        .order_by(Conversation.last_message_at.desc().nulls_last())
    )


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    user: CurrentUser,
    db: DbSession,
    status_filter: ConversationStatus | None = Query(default=None, alias="status"),
    flagged: bool | None = Query(default=None),
    needs_human: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationListItem]:
    query = _base_query().limit(limit).offset(offset)
    if status_filter is not None:
        query = query.where(Conversation.status == status_filter)
    if flagged is not None:
        query = query.where(Conversation.flagged_high_value == flagged)
    if needs_human is not None:
        query = query.where(Conversation.bot_active == (not needs_human))
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Customer.phone.ilike(pattern), Customer.name.ilike(pattern)))

    rows = (await db.execute(query)).all()
    items = []
    for conversation, phone, name in rows:
        preview = (
            await db.execute(
                select(Message.content_text, Message.transcription)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.id.desc())
                .limit(1)
            )
        ).first()
        preview_text = (preview[0] or preview[1] or "")[:80] if preview else None
        items.append(
            ConversationListItem(
                id=conversation.id,
                customer_id=conversation.customer_id,
                customer_phone=phone,
                customer_name=name,
                bot_active=conversation.bot_active,
                assigned_agent_id=conversation.assigned_agent_id,
                status=conversation.status,
                flagged_high_value=conversation.flagged_high_value,
                last_message_at=conversation.last_message_at,
                last_message_preview=preview_text,
            )
        )
    return items


async def _conversation_or_404(db: DbSession, conversation_id: int) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: int,
    user: CurrentUser,
    db: DbSession,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MessageOut]:
    await _conversation_or_404(db, conversation_id)
    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        query = query.where(Message.id < before_id)
    rows = (await db.execute(query)).scalars().all()
    return [MessageOut.model_validate(m) for m in reversed(rows)]


@router.post("/{conversation_id}/takeover", response_model=ConversationListItem)
async def take_over(
    conversation_id: int, user: CurrentUser, db: DbSession
) -> ConversationListItem:
    conversation = await _conversation_or_404(db, conversation_id)
    conversation.bot_active = False
    conversation.assigned_agent_id = user.id
    await record_audit(
        db, user_id=user.id, action="takeover", entity_type="conversation",
        entity_id=conversation.id,
    )
    await db.commit()
    event_bus.publish("conversation_updated", {"conversation_id": conversation.id})
    return await _list_item(db, conversation)


@router.post("/{conversation_id}/return-to-bot", response_model=ConversationListItem)
async def return_to_bot(
    conversation_id: int, user: CurrentUser, db: DbSession
) -> ConversationListItem:
    conversation = await _conversation_or_404(db, conversation_id)
    conversation.bot_active = True
    conversation.assigned_agent_id = None
    await record_audit(
        db, user_id=user.id, action="return_to_bot", entity_type="conversation",
        entity_id=conversation.id,
    )
    await db.commit()
    event_bus.publish("conversation_updated", {"conversation_id": conversation.id})
    return await _list_item(db, conversation)


@router.post("/{conversation_id}/close", response_model=ConversationListItem)
async def close_conversation(
    conversation_id: int, user: CurrentUser, db: DbSession
) -> ConversationListItem:
    conversation = await _conversation_or_404(db, conversation_id)
    conversation.status = ConversationStatus.CLOSED
    await record_audit(
        db, user_id=user.id, action="conversation_closed", entity_type="conversation",
        entity_id=conversation.id,
    )
    await db.commit()
    event_bus.publish("conversation_updated", {"conversation_id": conversation.id})
    return await _list_item(db, conversation)


@router.post("/{conversation_id}/reply", response_model=MessageOut)
async def agent_reply(
    conversation_id: int, body: AgentReply, user: CurrentUser, db: DbSession
) -> MessageOut:
    conversation = await _conversation_or_404(db, conversation_id)
    customer = await db.get(Customer, conversation.customer_id)
    try:
        await connector.send_text(customer.phone, body.text)
    except connector.ConnectorError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "WhatsApp connector unavailable"
        ) from exc
    message = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.AGENT,
        content_type=ContentType.TEXT,
        content_text=body.text,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message)
    event_bus.publish(
        "message",
        {"conversation_id": conversation.id, "message_id": message.id,
         "direction": "outbound"},
    )
    return MessageOut.model_validate(message)


async def _list_item(db: DbSession, conversation: Conversation) -> ConversationListItem:
    customer = await db.get(Customer, conversation.customer_id)
    return ConversationListItem(
        id=conversation.id,
        customer_id=conversation.customer_id,
        customer_phone=customer.phone,
        customer_name=customer.name,
        bot_active=conversation.bot_active,
        assigned_agent_id=conversation.assigned_agent_id,
        status=conversation.status,
        flagged_high_value=conversation.flagged_high_value,
        last_message_at=conversation.last_message_at,
    )


# --- websocket -----------------------------------------------------------

WS_AUTH_TIMEOUT_SECONDS = 5


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket) -> None:
    """Live event stream. First frame must be {"token": "<access JWT>"} —
    keeps tokens out of URLs and access logs.
    """
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_SECONDS
        )
        payload = decode_token(json.loads(raw).get("token", ""), expected_type="access")
        user_id = int(payload["sub"])
    except (TimeoutError, jwt.InvalidTokenError, json.JSONDecodeError, KeyError, ValueError):
        await websocket.close(code=4401)
        return

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return

    queue = event_bus.subscribe()
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except Exception as exc:  # noqa: BLE001 — disconnects arrive as varied exception types
        logger.debug("websocket closed: %s", type(exc).__name__)
    finally:
        event_bus.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await websocket.close()

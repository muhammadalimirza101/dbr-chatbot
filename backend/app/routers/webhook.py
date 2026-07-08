"""Inbound WhatsApp webhook (connector -> backend).

Protected by the shared secret header (timing-safe compare), rate-limited,
deduplicated on provider message id. Stores the message synchronously so
nothing is lost, then runs the AI pipeline as a background task so the
connector gets its 200 immediately.
"""

import hmac
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.dependencies import DbSession
from app.models import Conversation, Customer, Message
from app.models.enums import (
    ContentType,
    ConversationStatus,
    MessageDirection,
    SenderType,
)
from app.routers.auth import limiter
from app.schemas.webhook import InboundWebhook
from app.services.events import event_bus
from app.services.pipeline import process_inbound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

_CONTENT_TYPES = {
    "text": ContentType.TEXT,
    "voice": ContentType.VOICE,
    "image": ContentType.IMAGE,
}


def _check_secret(provided: str | None) -> None:
    expected = get_settings().connector_shared_secret
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@router.post("/whatsapp")
@limiter.limit("120/minute")
async def inbound_whatsapp(
    request: Request,
    body: InboundWebhook,
    db: DbSession,
    background: BackgroundTasks,
    x_connector_secret: str | None = Header(default=None),
) -> dict[str, str]:
    _check_secret(x_connector_secret)

    # dedup: Baileys can deliver the same message twice
    duplicate = (
        await db.execute(
            select(Message.id).where(Message.provider_message_id == body.provider_message_id)
        )
    ).first()
    if duplicate:
        return {"status": "duplicate"}

    customer = (
        await db.execute(select(Customer).where(Customer.phone == body.phone))
    ).scalar_one_or_none()
    if customer is None:
        customer = Customer(phone=body.phone)
        db.add(customer)
        await db.flush()

    conversation = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.customer_id == customer.id,
                Conversation.status == ConversationStatus.OPEN,
            )
            .order_by(Conversation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        await db.flush()

    message = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.CUSTOMER,
        content_type=_CONTENT_TYPES[body.content_type],
        content_text=body.text,
        provider_message_id=body.provider_message_id,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError:
        # lost a dedup race with a concurrent delivery of the same message
        await db.rollback()
        return {"status": "duplicate"}

    event_bus.publish(
        "message",
        {
            "conversation_id": conversation.id,
            "message_id": message.id,
            "direction": "inbound",
        },
    )
    background.add_task(
        process_inbound, message.id, body.media_base64, body.media_mime_type
    )
    return {"status": "ok"}

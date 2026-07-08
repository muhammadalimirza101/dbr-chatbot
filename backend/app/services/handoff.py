"""Human handoff: flip bot_active off, notify the dashboard, audit it."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation
from app.services.audit import record_audit
from app.services.events import event_bus

logger = logging.getLogger(__name__)

HANDOFF_MESSAGES = {
    "en": "Let me connect you with our team — someone will be with you shortly!",
    "roman_urdu": "Main aapko apni team se connect kar raha hoon — thori dair mein "
    "koi aap se raabta karega!",
}
HANDOFF_MESSAGES["ur"] = HANDOFF_MESSAGES["roman_urdu"]


async def hand_off_to_human(
    session: AsyncSession,
    conversation: Conversation,
    reason: str,
) -> None:
    """Deactivate the bot for this conversation and notify the dashboard.

    Caller commits. reason ∈ {customer_request, frustrated, bot_stuck,
    token_cap, high_value}.
    """
    if not conversation.bot_active:
        return
    conversation.bot_active = False
    await record_audit(
        session,
        user_id=None,  # system action
        action="bot_handoff",
        entity_type="conversation",
        entity_id=conversation.id,
        details={"reason": reason},
    )
    event_bus.publish(
        "handoff",
        {"conversation_id": conversation.id, "reason": reason},
    )
    logger.info("conversation %d handed off (%s)", conversation.id, reason)


def flag_high_value(conversation: Conversation) -> None:
    if not conversation.flagged_high_value:
        conversation.flagged_high_value = True
        event_bus.publish(
            "high_value_flagged", {"conversation_id": conversation.id}
        )

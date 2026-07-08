"""Inbound message pipeline.

transcribe (voice) -> analyze (nano: intent/language/slots) -> embed ->
KB similarity routing -> reply (cached KB answer or gpt-5.4-mini) ->
slot-filling -> lead creation -> handoff triggers -> token cap.

Runs as a background task with its own DB session, after the webhook has
stored the inbound message.
"""

import base64
import binascii
import logging
import re
from datetime import UTC, datetime, time
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models import (
    Conversation,
    Customer,
    KnowledgeBase,
    Lead,
    Message,
    UnansweredQuestion,
)
from app.models.enums import (
    ContentType,
    InterestType,
    LeadSource,
    LeadStage,
    MessageDirection,
    PreferredLanguage,
    SenderType,
)
from app.prompts.system import build_system_prompt, few_shot_turns
from app.services import connector
from app.services.ai import (
    MessageAnalysis,
    analyze_message,
    chat_reply,
    summarize_for_crm,
    transcribe_audio,
)
from app.services.audit import record_audit
from app.services.embeddings import embed_text, embedding_cache
from app.services.events import event_bus
from app.services.handoff import HANDOFF_MESSAGES, flag_high_value, hand_off_to_human

logger = logging.getLogger(__name__)

CACHE_THRESHOLD = 0.90
RAG_THRESHOLD = 0.75
HISTORY_WINDOW = 12

BOOKING_INTENTS = {"room_booking", "event_wedding", "corporate", "day_trip"}
HIGH_VALUE_INTENTS = {"event_wedding", "corporate"}
REQUIRED_SLOTS = ("dates", "party_size", "room_or_event_type")

_INTENT_TO_INTEREST = {
    "room_booking": InterestType.ROOM,
    "event_wedding": InterestType.EVENT_WEDDING,
    "corporate": InterestType.CORPORATE,
    "day_trip": InterestType.DAY_TRIP,
}


class Route(StrEnum):
    CACHE = "cache"  # >= 0.90: return the KB answer verbatim, no chat call
    RAG = "rag"  # 0.75-0.90 (or sales moment): KB context into mini
    OPEN = "open"  # < 0.75: conversational; log to unanswered_questions


def decide_route(best_similarity: float, is_sales_moment: bool, language: str) -> Route:
    """Threshold routing per CLAUDE.md.

    Sales moments (pricing/availability/booking) ALWAYS go through the model.
    Cached answers are English text, so non-English customers also route
    through the model to honour the reply-language rule.
    """
    if is_sales_moment:
        return Route.RAG
    if best_similarity >= CACHE_THRESHOLD:
        return Route.CACHE if language == "en" else Route.RAG
    if best_similarity >= RAG_THRESHOLD:
        return Route.RAG
    return Route.OPEN


def normalize_for_repeat_check(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


async def process_inbound(
    message_id: int, media_base64: str | None, media_mime: str | None
) -> None:
    """Background entrypoint. Own session; never raises into the caller."""
    try:
        async with async_session_factory() as session:
            await _process(session, message_id, media_base64, media_mime)
    except Exception:
        logger.exception("pipeline failed for message %d", message_id)


async def _process(
    session: AsyncSession,
    message_id: int,
    media_base64: str | None,
    media_mime: str | None,
) -> None:
    message = await session.get(Message, message_id)
    if message is None:
        return
    conversation = await session.get(Conversation, message.conversation_id)
    customer = await session.get(Customer, conversation.customer_id)

    # 1) voice -> Whisper transcription (stored even when the bot is off,
    #    so agents see readable text in the dashboard)
    if message.content_type == ContentType.VOICE and media_base64:
        try:
            audio = base64.b64decode(media_base64, validate=True)
            message.transcription = await transcribe_audio(
                audio, media_mime or "audio/ogg"
            )
            await session.commit()
            event_bus.publish(
                "transcription",
                {"conversation_id": conversation.id, "message_id": message.id},
            )
        except (binascii.Error, ValueError):
            logger.warning("undecodable voice payload for message %d", message.id)
        except Exception:
            logger.exception("transcription failed for message %d", message.id)

    effective_text = (message.content_text or message.transcription or "").strip()

    # 2) human has taken over: store-and-display only, never reply
    if not conversation.bot_active:
        return
    if not effective_text:
        return  # e.g. image without caption — nothing to answer

    # 3) per-conversation daily token cap
    settings = get_settings()
    spent_today = await _tokens_spent_today(session, conversation.id)
    if spent_today >= settings.daily_token_cap_per_conversation:
        language = _language_of(customer)
        await _send_and_store(
            session, conversation, customer,
            HANDOFF_MESSAGES.get(language, HANDOFF_MESSAGES["en"]), tokens=0,
        )
        await hand_off_to_human(session, conversation, reason="token_cap")
        await session.commit()
        return

    history_rows = await _recent_messages(session, conversation.id, before=message.id)
    transcript = _as_transcript(history_rows)

    # 4) nano: intent, language, slots, frustration
    analysis, nano_tokens = await analyze_message(transcript, effective_text)
    total_tokens = nano_tokens

    if analysis.language in PreferredLanguage:
        customer.preferred_language = PreferredLanguage(analysis.language)

    # 5) handoff triggers: explicit request, frustration, repeated question
    if analysis.wants_human or analysis.frustrated or _is_repeat(
        history_rows, effective_text
    ):
        reason = "customer_request" if analysis.wants_human else (
            "frustrated" if analysis.frustrated else "bot_stuck"
        )
        reply = HANDOFF_MESSAGES.get(analysis.language, HANDOFF_MESSAGES["en"])
        await _send_and_store(session, conversation, customer, reply, total_tokens)
        await hand_off_to_human(session, conversation, reason=reason)
        await session.commit()
        return

    # 6) weddings & corporate stay with the bot but get flagged for humans
    if analysis.intent in HIGH_VALUE_INTENTS:
        flag_high_value(conversation)

    # 7) embed + KB search + threshold routing
    query_embedding = await embed_text(effective_text)
    hits = embedding_cache.search(query_embedding, top_k=3)
    best_similarity = hits[0][1] if hits else 0.0
    is_sales_moment = (
        analysis.is_pricing_or_availability or analysis.intent in BOOKING_INTENTS
    )
    route = decide_route(best_similarity, is_sales_moment, analysis.language)

    kb_entries = await _kb_entries(session, [kb_id for kb_id, _ in hits])

    if route is Route.CACHE and kb_entries:
        reply = kb_entries[0].answer
    else:
        missing_slots = None
        if analysis.intent in BOOKING_INTENTS:
            missing_slots = [s for s in REQUIRED_SLOTS if s not in analysis.slots]
        kb_context = (
            [(e.question, e.answer) for e in kb_entries] if route is not Route.OPEN else []
        )
        system_prompt = build_system_prompt(analysis.language, kb_context, missing_slots)
        turns = [
            *few_shot_turns(),
            *_as_turns(history_rows),
            {"role": "user", "content": effective_text},
        ]
        reply, reply_tokens = await chat_reply(system_prompt, turns)
        total_tokens += reply_tokens

    if route is Route.OPEN and analysis.intent not in {"greeting", "other"}:
        session.add(
            UnansweredQuestion(
                conversation_id=conversation.id,
                question_text=effective_text[:2000],
                best_similarity_score=best_similarity,
            )
        )

    # 8) enough booking slots collected -> lead with nano CRM summary
    if analysis.intent in BOOKING_INTENTS and all(
        s in analysis.slots for s in REQUIRED_SLOTS
    ):
        summary_tokens = await _maybe_create_lead(
            session, conversation, customer, analysis,
            transcript + f"\nCustomer: {effective_text}",
        )
        total_tokens += summary_tokens

    await _send_and_store(session, conversation, customer, reply, total_tokens)
    await session.commit()


# --- helpers -------------------------------------------------------------


def _language_of(customer: Customer) -> str:
    return customer.preferred_language.value


async def _tokens_spent_today(session: AsyncSession, conversation_id: int) -> int:
    midnight = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return (
        await session.execute(
            select(func.coalesce(func.sum(Message.tokens_used), 0)).where(
                Message.conversation_id == conversation_id,
                Message.created_at >= midnight,
            )
        )
    ).scalar_one()


async def _recent_messages(
    session: AsyncSession, conversation_id: int, before: int
) -> list[Message]:
    rows = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id, Message.id < before)
                .order_by(Message.id.desc())
                .limit(HISTORY_WINDOW)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def _message_text(message: Message) -> str:
    return (message.content_text or message.transcription or "").strip()


def _as_transcript(rows: list[Message]) -> str:
    labels = {SenderType.CUSTOMER: "Customer", SenderType.BOT: "Bot", SenderType.AGENT: "Agent"}
    lines = [
        f"{labels[row.sender_type]}: {_message_text(row)}"
        for row in rows
        if _message_text(row)
    ]
    return "\n".join(lines) if lines else "(start of conversation)"


def _as_turns(rows: list[Message]) -> list[dict[str, str]]:
    turns = []
    for row in rows:
        text = _message_text(row)
        if not text:
            continue
        role = "user" if row.sender_type == SenderType.CUSTOMER else "assistant"
        turns.append({"role": role, "content": text})
    return turns


def _is_repeat(history: list[Message], newest: str) -> bool:
    """Same question twice in a row (and the bot already answered) = stuck."""
    previous_inbound = [
        m for m in history if m.direction == MessageDirection.INBOUND and _message_text(m)
    ]
    if not previous_inbound:
        return False
    return normalize_for_repeat_check(_message_text(previous_inbound[-1])) == (
        normalize_for_repeat_check(newest)
    )


async def _kb_entries(
    session: AsyncSession, kb_ids: list[int]
) -> list[KnowledgeBase]:
    if not kb_ids:
        return []
    rows = (
        (await session.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))))
        .scalars()
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[kb_id] for kb_id in kb_ids if kb_id in by_id]


async def _maybe_create_lead(
    session: AsyncSession,
    conversation: Conversation,
    customer: Customer,
    analysis: MessageAnalysis,
    transcript: str,
) -> int:
    interest = _INTENT_TO_INTEREST[analysis.intent]
    existing = (
        await session.execute(
            select(Lead.id).where(
                Lead.conversation_id == conversation.id,
                Lead.interest_type == interest,
                Lead.stage.not_in([LeadStage.WON, LeadStage.LOST]),
            )
        )
    ).first()
    if existing:
        return 0

    summary, tokens = await summarize_for_crm(transcript)
    if analysis.slots.get("name") and not customer.name:
        customer.name = str(analysis.slots["name"])[:120]
    lead = Lead(
        customer_id=customer.id,
        conversation_id=conversation.id,
        source=LeadSource.BOT,
        interest_type=interest,
        details=analysis.slots,
        ai_summary=summary,
    )
    session.add(lead)
    await session.flush()
    await record_audit(
        session, user_id=None, action="lead_auto_created", entity_type="lead",
        entity_id=lead.id, details={"interest_type": interest.value},
    )
    event_bus.publish(
        "lead_created", {"lead_id": lead.id, "conversation_id": conversation.id}
    )
    return tokens


async def _send_and_store(
    session: AsyncSession,
    conversation: Conversation,
    customer: Customer,
    text: str,
    tokens: int,
) -> None:
    try:
        await connector.send_text(customer.phone, text)
    except connector.ConnectorError as exc:
        # store the reply anyway so the dashboard shows what the bot intended;
        # agents can see delivery failed from the connector status panel
        logger.error("send failed for conversation %d: %s", conversation.id, exc)
    outbound = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.BOT,
        content_type=ContentType.TEXT,
        content_text=text,
        tokens_used=tokens or None,
    )
    session.add(outbound)
    conversation.last_message_at = datetime.now(UTC)
    await session.flush()
    event_bus.publish(
        "message",
        {
            "conversation_id": conversation.id,
            "message_id": outbound.id,
            "direction": "outbound",
        },
    )

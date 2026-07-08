"""Analytics for the dashboard. Aggregates only — no message content, no
phone numbers. All dates/hours are UTC; the UI converts to Asia/Karachi.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import Integer, cast, func, select

from app.dependencies import CurrentUser, DbSession
from app.models import Conversation, Lead, Message
from app.models.enums import LeadStage, MessageDirection, SenderType
from app.services import connector

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


@router.get("/overview")
async def overview(user: CurrentUser, db: DbSession) -> dict:
    since14, since30 = _days_ago(14), _days_ago(30)

    conversations_per_day = [
        {"date": str(day), "count": count}
        for day, count in (
            await db.execute(
                select(func.date(Conversation.created_at), func.count())
                .where(Conversation.created_at >= since14)
                .group_by(func.date(Conversation.created_at))
                .order_by(func.date(Conversation.created_at))
            )
        ).all()
    ]

    token_spend_per_day = [
        {"date": str(day), "tokens": int(tokens)}
        for day, tokens in (
            await db.execute(
                select(
                    func.date(Message.created_at),
                    func.coalesce(func.sum(Message.tokens_used), 0),
                )
                .where(Message.created_at >= since14)
                .group_by(func.date(Message.created_at))
                .order_by(func.date(Message.created_at))
            )
        ).all()
    ]

    route_counts = dict(
        (
            await db.execute(
                select(Message.pipeline_route, func.count())
                .where(
                    Message.created_at >= since30,
                    Message.sender_type == SenderType.BOT,
                    Message.pipeline_route.is_not(None),
                )
                .group_by(Message.pipeline_route)
            )
        ).all()
    )
    routed_total = sum(route_counts.values())

    leads_by_stage = {
        stage.value: 0 for stage in LeadStage
    } | {
        stage.value: count
        for stage, count in (
            await db.execute(select(Lead.stage, func.count()).group_by(Lead.stage))
        ).all()
    }
    leads_total = sum(leads_by_stage.values())

    # average first bot/agent response per conversation (last 30 days)
    first_in = (
        select(
            Message.conversation_id.label("cid"),
            func.min(Message.created_at).label("first_in"),
        )
        .where(Message.direction == MessageDirection.INBOUND)
        .group_by(Message.conversation_id)
        .subquery()
    )
    first_out = (
        select(
            Message.conversation_id.label("cid"),
            func.min(Message.created_at).label("first_out"),
        )
        .where(Message.direction == MessageDirection.OUTBOUND)
        .group_by(Message.conversation_id)
        .subquery()
    )
    avg_seconds = (
        await db.execute(
            select(
                func.avg(
                    func.extract("epoch", first_out.c.first_out - first_in.c.first_in)
                )
            )
            .select_from(
                first_in.join(first_out, first_in.c.cid == first_out.c.cid)
            )
            .where(
                first_out.c.first_out > first_in.c.first_in,
                first_in.c.first_in >= since30,
            )
        )
    ).scalar_one()

    busiest_hours_utc = [
        {"hour": int(hour), "count": count}
        for hour, count in (
            await db.execute(
                select(
                    cast(func.extract("hour", Message.created_at), Integer),
                    func.count(),
                )
                .where(
                    Message.created_at >= since30,
                    Message.direction == MessageDirection.INBOUND,
                )
                .group_by(cast(func.extract("hour", Message.created_at), Integer))
                .order_by(cast(func.extract("hour", Message.created_at), Integer))
            )
        ).all()
    ]

    won = leads_by_stage.get("won", 0)
    return {
        "conversations_per_day": conversations_per_day,
        "token_spend_per_day": token_spend_per_day,
        "cache_hit_rate": (
            round(route_counts.get("cache", 0) / routed_total, 3) if routed_total else None
        ),
        "route_counts": route_counts,
        "leads_by_stage": leads_by_stage,
        "lead_conversion_rate": round(won / leads_total, 3) if leads_total else None,
        "avg_first_response_seconds": (
            round(float(avg_seconds), 1) if avg_seconds is not None else None
        ),
        "busiest_hours_utc": busiest_hours_utc,
    }


@router.get("/connector-status")
async def connector_status(user: CurrentUser) -> dict:
    return {"connected": await connector.get_status()}

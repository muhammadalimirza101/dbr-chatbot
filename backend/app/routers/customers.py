"""Customer profiles. Agents and admins. Deleting a customer cascades all
their PII (conversations, messages, leads) — admin only, audit-logged.
"""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models import Conversation, Customer
from app.schemas.dashboard import ConversationListItem, CustomerOut, CustomerUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    user: CurrentUser,
    db: DbSession,
    search: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CustomerOut]:
    query = select(Customer).order_by(Customer.id.desc()).limit(limit).offset(offset)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(Customer.phone.ilike(pattern), Customer.name.ilike(pattern))
        )
    customers = (await db.execute(query)).scalars().all()
    return [CustomerOut.model_validate(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: int, user: CurrentUser, db: DbSession) -> CustomerOut:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}/conversations", response_model=list[ConversationListItem])
async def customer_conversations(
    customer_id: int, user: CurrentUser, db: DbSession
) -> list[ConversationListItem]:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    conversations = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.customer_id == customer_id)
                .order_by(Conversation.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ConversationListItem(
            id=c.id,
            customer_id=customer_id,
            customer_phone=customer.phone,
            customer_name=customer.name,
            bot_active=c.bot_active,
            assigned_agent_id=c.assigned_agent_id,
            status=c.status,
            flagged_high_value=c.flagged_high_value,
            last_message_at=c.last_message_at,
        )
        for c in conversations
    ]


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int, body: CustomerUpdate, user: CurrentUser, db: DbSession
) -> CustomerOut:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(customer, field, value)
    if changes:
        await record_audit(
            db, user_id=user.id, action="customer_updated", entity_type="customer",
            entity_id=customer.id, details={"fields": sorted(changes)},
        )
        await db.commit()
        await db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(customer_id: int, admin: AdminUser, db: DbSession) -> None:
    """Cascades conversations, messages, and leads (FK ON DELETE CASCADE)."""
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    await record_audit(
        db, user_id=admin.id, action="customer_deleted", entity_type="customer",
        entity_id=customer.id,
    )
    await db.delete(customer)
    await db.commit()

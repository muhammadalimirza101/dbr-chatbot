"""Lead pipeline (CRM). Agents and admins. Every change is audit-logged."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.models import Customer, Lead, User
from app.models.enums import InterestType, LeadSource, LeadStage
from app.schemas.dashboard import LeadCreate, LeadOut, LeadUpdate
from app.services.audit import record_audit
from app.services.events import event_bus

router = APIRouter(prefix="/leads", tags=["leads"])


async def _to_out(db: DbSession, lead: Lead) -> LeadOut:
    customer = await db.get(Customer, lead.customer_id)
    out = LeadOut.model_validate(lead)
    if customer:
        out.customer_phone = customer.phone
        out.customer_name = customer.name
    return out


@router.get("", response_model=list[LeadOut])
async def list_leads(
    user: CurrentUser,
    db: DbSession,
    stage: LeadStage | None = Query(default=None),
    interest_type: InterestType | None = Query(default=None),
    assigned_agent_id: int | None = Query(default=None),
    overdue: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[LeadOut]:
    query = select(Lead).order_by(Lead.updated_at.desc()).limit(limit).offset(offset)
    if stage is not None:
        query = query.where(Lead.stage == stage)
    if interest_type is not None:
        query = query.where(Lead.interest_type == interest_type)
    if assigned_agent_id is not None:
        query = query.where(Lead.assigned_agent_id == assigned_agent_id)
    if overdue:
        query = query.where(
            Lead.follow_up_at < datetime.now(UTC),
            Lead.stage.not_in([LeadStage.WON, LeadStage.LOST]),
        )
    leads = (await db.execute(query)).scalars().all()
    return [await _to_out(db, lead) for lead in leads]


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: int, user: CurrentUser, db: DbSession) -> LeadOut:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
    return await _to_out(db, lead)


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadCreate, user: CurrentUser, db: DbSession) -> LeadOut:
    customer = (
        await db.execute(select(Customer).where(Customer.phone == body.phone))
    ).scalar_one_or_none()
    if customer is None:
        customer = Customer(phone=body.phone, name=body.customer_name)
        db.add(customer)
        await db.flush()
    elif body.customer_name and not customer.name:
        customer.name = body.customer_name

    lead = Lead(
        customer_id=customer.id,
        source=LeadSource.MANUAL,
        interest_type=body.interest_type,
        details=body.details,
        follow_up_at=body.follow_up_at,
        assigned_agent_id=user.id,
    )
    db.add(lead)
    await db.flush()
    await record_audit(
        db, user_id=user.id, action="lead_created", entity_type="lead",
        entity_id=lead.id, details={"source": "manual"},
    )
    await db.commit()
    await db.refresh(lead)
    event_bus.publish("lead_created", {"lead_id": lead.id})
    return await _to_out(db, lead)


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: int, body: LeadUpdate, user: CurrentUser, db: DbSession
) -> LeadOut:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return await _to_out(db, lead)

    if "assigned_agent_id" in changes and changes["assigned_agent_id"] is not None:
        agent = await db.get(User, changes["assigned_agent_id"])
        if agent is None or not agent.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown agent")

    for field, value in changes.items():
        setattr(lead, field, value)
    await record_audit(
        db, user_id=user.id, action="lead_updated", entity_type="lead",
        entity_id=lead.id, details={"fields": sorted(changes)},
    )
    await db.commit()
    await db.refresh(lead)
    event_bus.publish("lead_updated", {"lead_id": lead.id})
    return await _to_out(db, lead)

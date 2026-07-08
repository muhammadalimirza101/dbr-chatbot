from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import InterestType, LeadSource, LeadStage, db_enum


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    source: Mapped[LeadSource] = mapped_column(db_enum(LeadSource, "lead_source"))
    interest_type: Mapped[InterestType] = mapped_column(
        db_enum(InterestType, "interest_type")
    )
    stage: Mapped[LeadStage] = mapped_column(
        db_enum(LeadStage, "lead_stage"),
        default=LeadStage.NEW,
        server_default=LeadStage.NEW.value,
        index=True,
    )
    # free-form slots: dates, party_size, room_type, budget — validated by
    # Pydantic schemas at the API boundary
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    ai_summary: Mapped[str | None] = mapped_column(Text)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="leads")  # noqa: F821

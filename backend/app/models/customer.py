from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import PreferredLanguage, db_enum


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    preferred_language: Mapped[PreferredLanguage] = mapped_column(
        db_enum(PreferredLanguage, "preferred_language"),
        default=PreferredLanguage.EN,
        server_default=PreferredLanguage.EN.value,
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="customer", passive_deletes=True
    )
    leads: Mapped[list["Lead"]] = relationship(  # noqa: F821
        back_populates="customer", passive_deletes=True
    )

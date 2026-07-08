from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import (
    ContentType,
    ConversationStatus,
    MessageDirection,
    SenderType,
    db_enum,
)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_status_last_message", "status", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    bot_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ConversationStatus] = mapped_column(
        db_enum(ConversationStatus, "conversation_status"),
        default=ConversationStatus.OPEN,
        server_default=ConversationStatus.OPEN.value,
    )
    flagged_high_value: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship(back_populates="conversations")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", passive_deletes=True
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    direction: Mapped[MessageDirection] = mapped_column(
        db_enum(MessageDirection, "message_direction")
    )
    sender_type: Mapped[SenderType] = mapped_column(db_enum(SenderType, "sender_type"))
    content_type: Mapped[ContentType] = mapped_column(db_enum(ContentType, "content_type"))
    content_text: Mapped[str | None] = mapped_column(Text)
    transcription: Mapped[str | None] = mapped_column(Text)
    media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    # provider message id from the connector, used to deduplicate deliveries
    provider_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

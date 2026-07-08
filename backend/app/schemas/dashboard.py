"""Request/response schemas for the dashboard API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ContentType,
    ConversationStatus,
    InterestType,
    LeadSource,
    LeadStage,
    MediaPurpose,
    MessageDirection,
    PreferredLanguage,
    SenderType,
    UserRole,
)

# --- conversations -------------------------------------------------------


class ConversationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_phone: str
    customer_name: str | None
    bot_active: bool
    assigned_agent_id: int | None
    status: ConversationStatus
    flagged_high_value: bool
    last_message_at: datetime | None
    last_message_preview: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    direction: MessageDirection
    sender_type: SenderType
    content_type: ContentType
    content_text: str | None
    transcription: str | None
    media_id: int | None
    tokens_used: int | None
    created_at: datetime


class AgentReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000)


# --- leads ---------------------------------------------------------------


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_phone: str | None = None
    customer_name: str | None = None
    conversation_id: int | None
    source: LeadSource
    interest_type: InterestType
    stage: LeadStage
    details: dict[str, Any]
    ai_summary: str | None
    assigned_agent_id: int | None
    follow_up_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(pattern=r"^\d{8,15}$")
    customer_name: str | None = Field(default=None, max_length=120)
    interest_type: InterestType
    details: dict[str, Any] = Field(default_factory=dict)
    follow_up_at: datetime | None = None

    # details is free-form but bounded
    def model_post_init(self, __context: Any) -> None:
        if len(str(self.details)) > 4000:
            raise ValueError("details too large")


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: LeadStage | None = None
    interest_type: InterestType | None = None
    assigned_agent_id: int | None = None
    follow_up_at: datetime | None = None
    details: dict[str, Any] | None = None
    ai_summary: str | None = Field(default=None, max_length=4000)


# --- customers -----------------------------------------------------------


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None
    preferred_language: PreferredLanguage
    tags: list[str]
    created_at: datetime


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    preferred_language: PreferredLanguage | None = None
    tags: list[str] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.tags is not None and (
            len(self.tags) > 20 or any(len(t) > 50 or not t.strip() for t in self.tags)
        ):
            raise ValueError("invalid tags")


# --- users (admin) -------------------------------------------------------


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=255)
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: UserRole


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


# --- media (admin) -------------------------------------------------------


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    mime_type: str
    size_bytes: int
    purpose: MediaPurpose
    created_at: datetime


# --- unanswered questions (admin) ---------------------------------------


class UnansweredOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    question_text: str
    best_similarity_score: float
    resolved: bool
    created_at: datetime


class ConvertToKB(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, min_length=3, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=2, max_length=50)

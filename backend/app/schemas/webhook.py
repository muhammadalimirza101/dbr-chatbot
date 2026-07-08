"""Inbound webhook payload from the connector (camelCase over the wire)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# 16 MB of media ≈ 22 MB base64
MAX_MEDIA_BASE64_CHARS = 23_000_000


class InboundWebhook(BaseModel):
    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, populate_by_name=True
    )

    phone: str = Field(pattern=r"^\d{8,15}$")
    content_type: Literal["text", "voice", "image"]
    text: str | None = Field(default=None, max_length=8000)
    media_base64: str | None = Field(default=None, max_length=MAX_MEDIA_BASE64_CHARS)
    media_mime_type: str | None = Field(default=None, max_length=100)
    provider_message_id: str = Field(min_length=1, max_length=128)
    timestamp: datetime

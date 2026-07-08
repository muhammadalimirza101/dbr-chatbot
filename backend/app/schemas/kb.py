from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KBCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=2, max_length=50)


class KBUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, min_length=3, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    is_active: bool | None = None


class KBOut(BaseModel):
    """Embedding is intentionally excluded — 1536 floats of internal state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    category: str
    is_active: bool
    has_embedding: bool = False
    created_by: int | None
    created_at: datetime
    updated_at: datetime

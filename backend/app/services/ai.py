"""Shared OpenAI async client.

Timeout and retry/backoff are handled by the SDK (exponential backoff on
429/5xx/connection errors). All OpenAI calls in the app go through this
client so limits are enforced in one place.
"""

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
CHAT_MODEL = "gpt-5.4-mini"
BACKGROUND_MODEL = "gpt-5.4-nano"


@lru_cache
def get_openai() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=get_settings().openai_api_key,
        timeout=30.0,
        max_retries=3,
    )

"""Phase 0 smoke test: app builds and /health responds.

Stub env vars are set before importing the app so no real .env or
database is required. /health/db is exercised manually against the
developer's local PostgreSQL instead.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://stub:stub@localhost:5432/stub"
)
os.environ.setdefault("OPENAI_API_KEY", "stub")
os.environ.setdefault("JWT_SECRET", "stub")
os.environ.setdefault("DASHBOARD_ORIGIN", "http://localhost:5173")
os.environ.setdefault("WHATSAPP_SESSION_DIR", "stub")
os.environ.setdefault("CONNECTOR_SHARED_SECRET", "stub")

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

"""Every dashboard endpoint must reject unauthenticated requests."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://stub:stub@localhost:5432/stub"
)
os.environ.setdefault("OPENAI_API_KEY", "stub")
os.environ.setdefault("JWT_SECRET", "stub")
os.environ.setdefault("DASHBOARD_ORIGIN", "http://localhost:5173")
os.environ.setdefault("WHATSAPP_SESSION_DIR", "stub")
os.environ.setdefault("CONNECTOR_SHARED_SECRET", "test-secret-value")

import httpx
import pytest

from app.main import app

PROTECTED_GETS = [
    "/conversations",
    "/conversations/1/messages",
    "/leads",
    "/leads/1",
    "/customers",
    "/customers/1",
    "/users",
    "/media",
    "/kb",
    "/kb/unanswered",
    "/analytics/overview",
    "/analytics/connector-status",
    "/auth/me",
]

PROTECTED_POSTS = [
    "/conversations/1/takeover",
    "/conversations/1/return-to-bot",
    "/conversations/1/reply",
    "/leads",
    "/kb",
    "/kb/unanswered/1/resolve",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_GETS)
async def test_get_requires_auth(path: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get(path)
    assert response.status_code == 401, path


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PROTECTED_POSTS)
async def test_post_requires_auth(path: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.post(path, json={})
    assert response.status_code == 401, path


@pytest.mark.asyncio
async def test_garbage_bearer_token_rejected() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get(
            "/conversations", headers={"Authorization": "Bearer not.a.jwt"}
        )
    assert response.status_code == 401

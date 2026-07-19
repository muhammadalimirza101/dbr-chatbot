"""Webhook security: secret required, payload validated.

Uses the stub env from test_health (no DB rows are touched — requests are
rejected before any query runs).
"""

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

PAYLOAD = {
    "phone": "923001234567",
    "contentType": "text",
    "text": "hello",
    "providerMessageId": "TEST123",
    "timestamp": "2026-07-08T12:00:00Z",
}


@pytest.fixture
def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret(client: httpx.AsyncClient) -> None:
    async with client as c:
        response = await c.post("/webhook/whatsapp", json=PAYLOAD)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(client: httpx.AsyncClient) -> None:
    async with client as c:
        response = await c.post(
            "/webhook/whatsapp",
            json=PAYLOAD,
            headers={"x-connector-secret": "wrong-value"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_bad_phone(client: httpx.AsyncClient) -> None:
    async with client as c:
        response = await c.post(
            "/webhook/whatsapp",
            json={**PAYLOAD, "phone": "not-a-phone'; DROP TABLE customers;--"},
            headers={"x-connector-secret": "test-secret-value"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_rejects_unknown_fields(client: httpx.AsyncClient) -> None:
    async with client as c:
        response = await c.post(
            "/webhook/whatsapp",
            json={**PAYLOAD, "unexpected": "field"},
            headers={"x-connector-secret": "test-secret-value"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_media_requires_secret(client: httpx.AsyncClient) -> None:
    async with client as c:
        response = await c.get("/internal/media/1")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        ("/internal/wa-auth/get", {"keys": ["creds"]}),
        ("/internal/wa-auth/set", {"values": {"creds": "x"}}),
        ("/internal/wa-auth/clear", {}),
    ],
)
async def test_wa_auth_requires_secret(
    client: httpx.AsyncClient, path: str, body: dict
) -> None:
    async with client as c:
        response = await c.post(path, json=body)
    assert response.status_code == 401

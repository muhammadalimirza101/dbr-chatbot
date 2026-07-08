"""HTTP client for the WhatsApp connector's internal API (localhost).

The connector is transport-only; this client is the single place the
backend talks to it, so swapping to the Cloud API later touches only
this file and the connector itself.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_SECRET_HEADER = "x-connector-secret"  # noqa: S105 — header name, not a secret


class ConnectorError(Exception):
    """The connector could not deliver the message."""


async def _post_send(payload: dict) -> None:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.connector_url}/send",
                json=payload,
                headers={_SECRET_HEADER: settings.connector_shared_secret},
            )
    except httpx.HTTPError as exc:
        raise ConnectorError(f"connector unreachable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise ConnectorError(f"connector returned HTTP {response.status_code}")


async def send_text(phone: str, text: str) -> None:
    await _post_send({"kind": "text", "phone": phone, "text": text})


async def send_media(
    phone: str, media_id: int, media_type: str, caption: str | None = None
) -> None:
    await _post_send(
        {
            "kind": "media",
            "phone": phone,
            "mediaId": str(media_id),
            "mediaType": media_type,
            "caption": caption,
        }
    )


async def send_location(
    phone: str, latitude: float, longitude: float, name: str | None = None
) -> None:
    await _post_send(
        {
            "kind": "location",
            "phone": phone,
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
        }
    )


async def get_status() -> bool:
    """True when the connector reports an open WhatsApp connection."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{settings.connector_url}/status",
                headers={_SECRET_HEADER: settings.connector_shared_secret},
            )
        return response.status_code == 200 and response.json().get("connected", False)
    except httpx.HTTPError:
        return False

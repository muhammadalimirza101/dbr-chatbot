"""In-process pub/sub bus for live dashboard updates.

Phase 5's websocket endpoint subscribes here. Single-process by design —
matches the single-instance deployment. Payloads reference conversations by
internal id; they go only to authenticated dashboard clients, never to logs.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, **payload}
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # slow consumer: drop it rather than block the pipeline
                self._subscribers.discard(queue)
                logger.warning("dropped slow event subscriber")


event_bus = EventBus()

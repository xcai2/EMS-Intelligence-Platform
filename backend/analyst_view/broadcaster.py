"""
In-memory SSE broadcaster for Analyst View.

All connected SSE clients subscribe with an asyncio.Queue.
When the scheduler warms the cache it calls broadcast_update() and
every client receives a 'cache_refreshed' push event.

Usage
-----
    from backend.analyst_view.broadcaster import broadcast_update

    await broadcast_update("cache_refreshed", {"cached_at": "...", "companies": 12})
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_subscribers: list[asyncio.Queue] = []


def subscribe() -> asyncio.Queue:
    """Register a new SSE client and return its queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    _subscribers.append(q)
    logger.debug(f"[broadcaster] client subscribed ({len(_subscribers)} total)")
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a client queue on disconnect."""
    try:
        _subscribers.remove(q)
        logger.debug(f"[broadcaster] client unsubscribed ({len(_subscribers)} remaining)")
    except ValueError:
        pass


async def broadcast_update(event: str, data: dict) -> None:
    """Push an event to every subscribed SSE client."""
    if not _subscribers:
        return
    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait({"event": event, "data": data})
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        unsubscribe(q)
    logger.info(f"[broadcaster] '{event}' → {len(_subscribers)} client(s)")


def subscriber_count() -> int:
    return len(_subscribers)

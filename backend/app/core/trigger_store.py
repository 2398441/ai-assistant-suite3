"""
In-memory fanout queue for delivering Composio trigger events to
frontend clients via SSE.  Each browser tab that opens the SSE stream
registers its own asyncio.Queue; when a trigger fires we put the event
onto every queue for that user.

Pending buffer: events published while no SSE stream is connected are
held for up to PENDING_TTL seconds so they are delivered as soon as
the client connects (e.g. summariser fires before the SSE stream opens).
"""

import asyncio
import json
import time
from collections import defaultdict
from typing import AsyncGenerator

from ..config.settings import settings

# email → list of open SSE queues
_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

# email → list of (timestamp, event) buffered while no consumer is open
_pending: dict[str, list[tuple[float, dict]]] = defaultdict(list)


def publish(email: str, event: dict) -> None:
    """Deliver a trigger event to all open SSE streams for this user.
    If no stream is open, buffer the event for later delivery."""
    queues = _queues.get(email, [])
    if queues:
        for q in queues:
            q.put_nowait(event)
    else:
        _pending[email].append((time.monotonic(), event))


async def subscribe(email: str) -> asyncio.Queue:
    """Register a new SSE queue for this user, drain any pending events,
    and return the queue."""
    q: asyncio.Queue = asyncio.Queue()
    _queues[email].append(q)

    # Drain buffered events that arrived before this stream connected
    now = time.monotonic()
    fresh = [(ts, ev) for ts, ev in _pending.get(email, []) if now - ts < settings.pending_event_ttl]
    _pending[email] = []
    for _, ev in fresh:
        q.put_nowait(ev)

    return q


def unsubscribe(email: str, q: asyncio.Queue) -> None:
    """Remove a closed SSE queue."""
    try:
        _queues[email].remove(q)
    except (KeyError, ValueError):
        pass


async def sse_generator(email: str) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings until the client
    disconnects.  Sends a keepalive comment every N seconds (configured via
    settings.sse_keepalive_interval) to prevent proxy timeouts.
    """
    q = await subscribe(email)
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=settings.sse_keepalive_interval)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(email, q)

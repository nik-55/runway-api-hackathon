import asyncio
from typing import Any

from app import db
from app.logging_setup import get_logger

log = get_logger(__name__)


_subscribers: dict[str, list[asyncio.Queue]] = {}
_lock = asyncio.Lock()


async def subscribe(session_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    async with _lock:
        _subscribers.setdefault(session_id, []).append(q)
    return q


async def unsubscribe(session_id: str, q: asyncio.Queue) -> None:
    async with _lock:
        lst = _subscribers.get(session_id, [])
        if q in lst:
            lst.remove(q)
        if not lst:
            _subscribers.pop(session_id, None)


def publish(session_id: str, type_: str, payload: dict[str, Any]) -> None:
    """Persist event and fan out to subscribers (sync wrapper)."""
    ev = db.append_event(session_id, type_, payload)
    log.debug("event %s seq=%d type=%s", session_id, ev.seq, type_)
    subs = _subscribers.get(session_id, [])
    msg = {"id": ev.seq, "type": type_, "payload": payload, "created_at": ev.created_at}
    for q in list(subs):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            log.warning("dropping event for slow subscriber on %s", session_id)

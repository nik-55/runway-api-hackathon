import asyncio
import json
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sse_starlette.sse import EventSourceResponse

from app import db
from app.logging_setup import get_logger
from app.pipeline import events, runner

log = get_logger(__name__)
router = APIRouter()


_YT_RE = re.compile(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)


def _parse_time(value: str | None) -> float | None:
    """Parse '1:30', '90', '1:30:00' into seconds. Returns None if blank."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None


@router.post("/sessions")
async def create_session(
    youtube_url: str = Form(...),
    direction: str | None = Form(None),
    clip_start: str | None = Form(None),
    clip_end: str | None = Form(None),
):
    youtube_url = youtube_url.strip()
    if not _YT_RE.search(youtube_url):
        return RedirectResponse("/?error=invalid_url", status_code=303)
    direction = (direction or "").strip() or None
    clip_start_sec = _parse_time(clip_start)
    clip_end_sec = _parse_time(clip_end)

    session_id = uuid.uuid4().hex
    db.create_session(session_id, youtube_url, direction, clip_start_sec, clip_end_sec)
    asyncio.create_task(runner.run(session_id))
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str):
    sess = db.get_session(session_id)
    if not sess:
        return RedirectResponse("/", status_code=303)
    if sess.status not in ("failed", "queued"):
        return RedirectResponse(f"/sessions/{session_id}", status_code=303)
    db.update_session(session_id, status="queued", failure=None)
    asyncio.create_task(runner.run(session_id))
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.get("/sessions/{session_id}/events")
async def session_events(request: Request, session_id: str, last_event_id: int = 0):
    last_seq = int(request.headers.get("Last-Event-ID", last_event_id) or 0)

    async def _gen() -> AsyncGenerator[dict, None]:
        # backfill anything the client missed
        for ev in db.list_events(session_id, after_seq=last_seq):
            yield {
                "event": ev.type,
                "id": str(ev.seq),
                "data": json.dumps({"type": ev.type, "payload": ev.payload, "created_at": ev.created_at}),
            }
        q = await events.subscribe(session_id)
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {
                        "event": msg["type"],
                        "id": str(msg["id"]),
                        "data": json.dumps(msg),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
        finally:
            await events.unsubscribe(session_id, q)

    return EventSourceResponse(_gen())

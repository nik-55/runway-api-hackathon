import asyncio
import json
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sse_starlette.sse import EventSourceResponse

from app import db
from app.config import settings
from app.logging_setup import get_logger
from app.pipeline import events, runner
from app.pipeline.youtube import ffprobe_duration

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
    youtube_url: str | None = Form(None),
    video_file: UploadFile | None = File(None),
    direction: str | None = Form(None),
    clip_start: str | None = Form(None),
    clip_end: str | None = Form(None),
):
    youtube_url = (youtube_url or "").strip()
    has_file = bool(video_file and video_file.filename)

    if not youtube_url and not has_file:
        return RedirectResponse("/?error=no_input", status_code=303)
    if youtube_url and not _YT_RE.search(youtube_url):
        return RedirectResponse("/?error=invalid_url", status_code=303)

    direction = (direction or "").strip() or None
    clip_start_sec = _parse_time(clip_start)
    clip_end_sec = _parse_time(clip_end)

    session_id = uuid.uuid4().hex

    if has_file:
        out_dir = settings.session_dir(session_id)
        out_path = out_dir / "source.mp4"
        try:
            with out_path.open("wb") as fh:
                while True:
                    chunk = await video_file.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
        finally:
            await video_file.close()

        try:
            duration = await ffprobe_duration(out_path)
        except Exception:
            out_path.unlink(missing_ok=True)
            return RedirectResponse("/?error=invalid_video", status_code=303)
        if duration <= 0:
            out_path.unlink(missing_ok=True)
            return RedirectResponse("/?error=invalid_video", status_code=303)
        if duration > settings.max_video_duration_sec:
            out_path.unlink(missing_ok=True)
            return RedirectResponse("/?error=too_long", status_code=303)

        url_label = f"upload:{video_file.filename}"
        db.create_session(session_id, url_label, direction, clip_start_sec, clip_end_sec)
    else:
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

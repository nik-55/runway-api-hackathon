from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.config import REPO_ROOT, settings

router = APIRouter()
templates = Jinja2Templates(directory=str(REPO_ROOT / "app" / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sessions = db.list_sessions(limit=50)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sessions": sessions,
            "max_video_minutes": settings.max_video_duration_sec // 60,
        },
    )


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: str):
    sess = db.get_session(session_id)
    if not sess:
        return HTMLResponse(f"session {session_id} not found", status_code=404)
    events = db.list_events(session_id)
    return templates.TemplateResponse(
        request,
        "session.html",
        {"session": sess, "events": events},
    )

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import db
from app.config import REPO_ROOT, settings

router = APIRouter()
templates = Jinja2Templates(directory=str(REPO_ROOT / "app" / "templates"))


SHOWCASE_ORDER = [
    "roast-this-project-itself",
    "bamboo-sleep-repeat-a-Panda-life-plan",
    "When-the-Pentagon-Finally-Admits-Aliens",
    "Two-Chatbot-Companies-Worth-More-Than-Most-Countries-What-Could-Go-Wrong",
]


def _list_showcase_reels(limit: int = 5):
    showcase_dir = settings.media_root / "example-generations"
    if not showcase_dir.is_dir():
        return []
    order_index = {slug: i for i, slug in enumerate(SHOWCASE_ORDER)}

    def sort_key(p):
        return (order_index.get(p.parent.name, len(order_index)), -p.stat().st_mtime)

    reels = sorted(showcase_dir.glob("*/reel.mp4"), key=sort_key)[:limit]
    items = []
    for reel in reels:
        slug = reel.parent.name
        poster = reel.with_name("poster.jpg")
        items.append({
            "slug": slug,
            "title": slug.replace("-", " ").replace("_", " ").strip().capitalize(),
            "video_url": f"/media/example-generations/{slug}/reel.mp4",
            "poster_url": f"/media/example-generations/{slug}/poster.jpg" if poster.exists() else None,
        })
    return items


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sessions = db.list_sessions(limit=50)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sessions": sessions,
            "max_video_minutes": settings.max_video_duration_sec // 60,
            "showcase_reels": _list_showcase_reels(),
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

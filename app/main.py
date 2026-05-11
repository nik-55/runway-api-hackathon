import logging
import subprocess

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import settings
from app.logging_setup import setup_logging
from app.routes import pages, sessions

log = logging.getLogger(__name__)


def _generate_showcase_posters() -> None:
    showcase_dir = settings.media_root / "example-generations"
    if not showcase_dir.is_dir():
        return
    for reel in showcase_dir.glob("*/reel.mp4"):
        poster = reel.with_name("poster.jpg")
        if poster.exists():
            continue
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", "2", "-i", str(reel),
             "-frames:v", "1", "-q:v", "3", "-vf", "scale=540:-2",
             str(poster)],
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            log.warning("showcase poster gen failed for %s: %s", reel, result.stderr.decode("utf-8", "ignore").strip())


def create_app() -> FastAPI:
    setup_logging()
    db.init_db()
    app = FastAPI(title="ReelAgent")
    app.include_router(pages.router)
    app.include_router(sessions.router)
    app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")
    _generate_showcase_posters()
    return app


app = create_app()

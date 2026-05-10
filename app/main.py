from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import settings
from app.logging_setup import setup_logging
from app.routes import pages, sessions


def create_app() -> FastAPI:
    setup_logging()
    db.init_db()
    app = FastAPI(title="ReelAgent")
    app.include_router(pages.router)
    app.include_router(sessions.router)
    app.mount("/media", StaticFiles(directory=str(settings.media_root)), name="media")
    return app


app = create_app()

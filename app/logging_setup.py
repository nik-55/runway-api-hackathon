import contextvars
import logging
from logging.handlers import RotatingFileHandler

from app.config import settings


_session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)


def set_session_id(session_id: str | None) -> None:
    _session_id_var.set(session_id)


class SessionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id_var.get() or "-"
        return True


_LOG_FORMAT = "%(asctime)s %(levelname)s [%(session_id)s] %(name)s: %(message)s"

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    fmt = logging.Formatter(_LOG_FORMAT)
    session_filter = SessionFilter()

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.addFilter(session_filter)

    file_path = settings.logs_root / "app.log"
    rotating = RotatingFileHandler(
        str(file_path), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    rotating.setFormatter(fmt)
    rotating.addFilter(session_filter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(stream)
    root.addHandler(rotating)

    logging.getLogger("app").setLevel(logging.DEBUG)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

import functools
import json
from typing import Any, Callable, Awaitable

from app import db
from app.logging_setup import get_logger

log = get_logger(__name__)


async def checkpointed(
    session_id: str,
    step_key: str,
    fn: Callable[..., Awaitable[Any]],
    *args,
    **kwargs,
) -> Any:
    cached = db.get_step_result(session_id, step_key)
    if cached and cached["status"] == "completed":
        log.info("checkpoint hit: %s", step_key)
        return cached["result"]
    try:
        result = await fn(*args, **kwargs)
    except Exception as e:
        db.put_step_result(session_id, step_key, "failed", {"error": str(e), "type": type(e).__name__})
        raise
    db.put_step_result(session_id, step_key, "completed", result)
    return result

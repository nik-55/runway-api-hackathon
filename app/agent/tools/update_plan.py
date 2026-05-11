from app.agent.context import SessionCtx
from app.logging_setup import get_logger
from app.pipeline.events import publish

log = get_logger(__name__)


async def call(ctx: SessionCtx, *, plan: str) -> dict:
    text = (plan or "").strip()
    publish(ctx.session_id, "agent.plan", {"plan": text})
    log.info("plan updated for session %s (%d chars)", ctx.session_id, len(text))
    return {"ok": True}

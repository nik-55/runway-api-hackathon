import asyncio
import uuid

from app.agent.context import SessionCtx
from app.agent.runway_client import download_to_async, get_client
from app.logging_setup import get_logger

log = get_logger(__name__)

_RATIO = "720:1280"
_MODEL = "gen4.5"
_VALID_DURATIONS = (4, 6, 8)


def _create_and_wait(prompt: str, duration: int):
    client = get_client()
    task = client.text_to_video.create(
        model=_MODEL,
        prompt_text=prompt,
        ratio=_RATIO,
        duration=duration,
    ).wait_for_task_output()
    return task


async def call(ctx: SessionCtx, *, prompt: str, duration: int) -> dict:
    if duration not in _VALID_DURATIONS:
        # snap to nearest valid duration
        duration = min(_VALID_DURATIONS, key=lambda v: abs(v - int(duration)))
    log.info("text_to_video: %r duration=%d", prompt[:120], duration)
    task = await asyncio.to_thread(_create_and_wait, prompt, duration)
    output = getattr(task, "output", None) or []
    if not output:
        return {"error": "no output URL", "task_id": getattr(task, "id", None)}
    url = output[0]

    asset_id = uuid.uuid4().hex[:12]
    out_path = ctx.tools_dir / f"animated_{asset_id}.mp4"
    await download_to_async(url, str(out_path))
    ctx.register_asset(asset_id, "video", str(out_path), float(duration), "generate_animated_reaction")
    return {"asset_id": asset_id, "duration_sec": int(duration)}

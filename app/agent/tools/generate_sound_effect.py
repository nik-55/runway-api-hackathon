import asyncio
import uuid

from app.agent.context import SessionCtx
from app.agent.runway_client import download_to_async, get_client
from app.logging_setup import get_logger

log = get_logger(__name__)


def _create_and_wait(prompt: str, duration: float):
    client = get_client()
    task = client.sound_effect.create(
        model="eleven_text_to_sound_v2",
        prompt_text=prompt,
        duration=duration,
    ).wait_for_task_output()
    return task


async def call(ctx: SessionCtx, *, prompt: str, duration: float) -> dict:
    duration = max(0.5, min(22.0, float(duration)))
    log.info("sound_effect: %r duration=%.2f", prompt[:120], duration)
    task = await asyncio.to_thread(_create_and_wait, prompt, duration)
    output = getattr(task, "output", None) or []
    if not output:
        return {"error": "no output URL", "task_id": getattr(task, "id", None)}
    url = output[0]

    asset_id = uuid.uuid4().hex[:12]
    out_path = ctx.tools_dir / f"sfx_{asset_id}.mp3"
    await download_to_async(url, str(out_path))
    ctx.register_asset(asset_id, "audio", str(out_path), duration, "generate_sound_effect")
    return {"asset_id": asset_id, "duration_sec": duration}

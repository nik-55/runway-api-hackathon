import asyncio
import uuid

from app.agent.context import SessionCtx
from app.agent.runway_client import download_to_async, get_client
from app.logging_setup import get_logger

log = get_logger(__name__)

_RATIO = "720:1280"
_MODEL = "gen4_image"


def _create_and_wait(prompt: str):
    client = get_client()
    task = client.text_to_image.create(
        model=_MODEL,
        prompt_text=prompt,
        ratio=_RATIO,
    ).wait_for_task_output()
    return task


async def call(ctx: SessionCtx, *, prompt: str) -> dict:
    log.info("text_to_image: %r", prompt[:120])
    task = await asyncio.to_thread(_create_and_wait, prompt)
    output = getattr(task, "output", None) or []
    if not output:
        return {"error": "no output URL", "task_id": getattr(task, "id", None)}
    url = output[0]

    asset_id = uuid.uuid4().hex[:12]
    out_path = ctx.tools_dir / f"reaction_image_{asset_id}.png"
    await download_to_async(url, str(out_path))

    ctx.register_asset(asset_id, "image", str(out_path), None, "generate_reaction_image")
    return {"asset_id": asset_id, "duration_sec": None}

import asyncio
import uuid

from app.agent.context import SessionCtx
from app.agent.runway_client import download_to_async, get_client
from app.logging_setup import get_logger
from app.pipeline.youtube import ffprobe_duration, slice_audio

log = get_logger(__name__)


def _upload_and_isolate(file_path: str):
    client = get_client()
    with open(file_path, "rb") as f:
        upload = client.uploads.create_ephemeral(file=f)
    runway_uri = getattr(upload, "runway_uri", None) or getattr(upload, "uri", None)
    if not runway_uri:
        raise RuntimeError("upload did not return a runway:// uri")
    task = client.voice_isolation.create(
        model="eleven_voice_isolation",
        audio_uri=runway_uri,
    ).wait_for_task_output()
    return task


async def call(ctx: SessionCtx, *, start_sec: float, end_sec: float) -> dict:
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec + 0.5, float(end_sec))
    if ctx.source_duration_sec:
        end_sec = min(end_sec, ctx.source_duration_sec)

    asset_id = uuid.uuid4().hex[:12]
    sliced = ctx.tools_dir / f"slice_{asset_id}.m4a"
    await slice_audio(ctx.source_audio_path, start_sec, end_sec, sliced)

    log.info("voice_isolation: %.2f-%.2f (%.2fs)", start_sec, end_sec, end_sec - start_sec)
    task = await asyncio.to_thread(_upload_and_isolate, str(sliced))
    output = getattr(task, "output", None) or []
    if not output:
        return {"error": "no output URL", "task_id": getattr(task, "id", None)}
    url = output[0]

    out_path = ctx.tools_dir / f"isolated_{asset_id}.mp3"
    await download_to_async(url, str(out_path))
    duration = await ffprobe_duration(out_path)
    ctx.register_asset(asset_id, "audio", str(out_path), duration, "isolate_voice")
    return {
        "asset_id": asset_id,
        "duration_sec": round(duration, 2),
        "window": [start_sec, end_sec],
    }

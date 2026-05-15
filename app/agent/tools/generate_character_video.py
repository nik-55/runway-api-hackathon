import asyncio
import uuid

from app.agent.context import SessionCtx
from app.agent.runway_client import download_to_async, get_client
from app.config import settings
from app.logging_setup import get_logger
from app.pipeline.youtube import ffprobe_duration

log = get_logger(__name__)

_VALID_VOICES = {
    "victoria", "vincent", "clara", "drew", "skye", "max", "morgan", "felix",
    "mia", "marcus", "summer", "ruby", "aurora", "jasper", "leo", "adrian",
    "nina", "emma", "blake", "david", "maya", "nathan", "sam", "georgia",
    "petra", "adam", "zach", "violet", "roman", "luna",
}


def _create_and_wait(script: str, avatar_id: str, voice_preset: str):
    client = get_client()
    task = client.avatar_videos.create(
        model="gwm1_avatars",
        avatar={"type": "custom", "avatarId": avatar_id},
        speech={
            "type": "text",
            "text": script,
            "voice": {"type": "preset", "presetId": voice_preset},
        },
    ).wait_for_task_output()
    return task


async def call(ctx: SessionCtx, *, script: str, voice_preset: str | None = None) -> dict:
    voice = (voice_preset or settings.character_voice_preset).strip().lower()
    if voice not in _VALID_VOICES:
        log.warning("voice_preset %r not in known set; falling back to default", voice)
        voice = settings.character_voice_preset
    avatar_id = settings.character_avatar_preset
    log.info("avatar_videos: avatar_id=%s voice=%s script_len=%d", avatar_id, voice, len(script))
    task = await asyncio.to_thread(_create_and_wait, script, avatar_id, voice)
    output = getattr(task, "output", None) or []
    if not output:
        return {"error": "no output URL", "task_id": getattr(task, "id", None)}
    url = output[0]

    asset_id = uuid.uuid4().hex[:12]
    out_path = ctx.tools_dir / f"character_{asset_id}.mp4"
    await download_to_async(url, str(out_path))

    duration = await ffprobe_duration(out_path)
    ctx.register_asset(asset_id, "video", str(out_path), duration, "generate_character_video")
    return {"asset_id": asset_id, "duration_sec": round(duration, 2)}

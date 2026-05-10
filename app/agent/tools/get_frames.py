import uuid
from pathlib import Path

from app.agent.context import SessionCtx
from app.llm.vision_client import ask_vision
from app.logging_setup import get_logger
from app.pipeline.youtube import extract_frames

log = get_logger(__name__)


_MAX_FRAMES = 6


async def call(ctx: SessionCtx, *, start_sec: float, end_sec: float, prompt: str) -> dict:
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec + 0.5, float(end_sec))
    if ctx.source_duration_sec:
        end_sec = min(end_sec, ctx.source_duration_sec)
        start_sec = min(start_sec, max(0.0, end_sec - 0.5))

    frames_dir = ctx.session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:8]
    pattern = frames_dir / f"{stem}_%03d.jpg"

    duration = end_sec - start_sec
    n = max(1, min(_MAX_FRAMES, int(round(duration / 1.0)) or 1))

    files = await extract_frames(
        ctx.source_video_path, start_sec, end_sec, n, str(pattern)
    )
    if not files:
        return {"error": "no frames extracted"}

    answer = await ask_vision(prompt, files)
    log.info("get_frames %.1f-%.1f n=%d -> %d chars", start_sec, end_sec, len(files), len(answer))
    return {"answer": answer, "frame_count": len(files), "window": [start_sec, end_sec]}

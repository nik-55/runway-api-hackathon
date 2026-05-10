import json
import traceback
from pathlib import Path

from app import db
from app.agent.context import SessionCtx
from app.agent.loop import run_agent_loop
from app.config import settings
from app.logging_setup import get_logger, set_session_id
from app.pipeline import assemble, transcribe, youtube
from app.pipeline.checkpoints import checkpointed
from app.pipeline.events import publish

log = get_logger(__name__)


async def _step(session_id: str, name: str, key: str, fn, *args, **kwargs):
    publish(session_id, "step.started", {"name": name})
    try:
        result = await checkpointed(session_id, key, fn, *args, **kwargs)
    except Exception as e:
        publish(session_id, "step.failed", {"name": name, "error": str(e), "type": type(e).__name__})
        raise
    publish(session_id, "step.completed", {"name": name, "result": result})
    return result


def _seed_assets_from_step_results(ctx: SessionCtx) -> None:
    """When resuming, replay completed tool step_results into ctx.assets."""
    rows = db.list_step_results(ctx.session_id, prefix="tool:")
    for r in rows:
        if r["status"] != "completed":
            continue
        result = r["result"]
        if not isinstance(result, dict):
            continue
        asset_id = result.get("asset_id")
        if not asset_id:
            continue
        # We need to know paths — they are derivable from the tool name and asset_id.
        tools_dir = ctx.tools_dir
        candidates = [
            ("video", tools_dir / f"animated_{asset_id}.mp4", "generate_animated_reaction"),
            ("video", tools_dir / f"character_{asset_id}.mp4", "generate_character_video"),
            ("image", tools_dir / f"reaction_image_{asset_id}.png", "generate_reaction_image"),
            ("audio", tools_dir / f"sfx_{asset_id}.mp3", "generate_sound_effect"),
            ("audio", tools_dir / f"isolated_{asset_id}.mp3", "isolate_voice"),
        ]
        for kind, path, tool in candidates:
            if path.exists():
                ctx.register_asset(asset_id, kind, str(path), result.get("duration_sec"), tool)
                break


async def run(session_id: str) -> None:
    set_session_id(session_id)
    sess = db.get_session(session_id)
    if sess is None:
        raise RuntimeError(f"session {session_id} not found")
    db.update_session(session_id, status="running")
    publish(session_id, "session.started", {"youtube_url": sess.youtube_url, "direction": sess.direction})

    ctx = SessionCtx(session_id=session_id, direction=sess.direction)

    try:
        # Pre-agent stage
        dl = await _step(session_id, "download_video", "download_video",
                         youtube.download_video, session_id, sess.youtube_url)
        ctx.source_video_path = dl["path"]
        ctx.source_duration_sec = float(dl.get("duration_sec") or 0.0)

        if sess.clip_start_sec is not None or sess.clip_end_sec is not None:
            clip_start = sess.clip_start_sec or 0.0
            clip_end = sess.clip_end_sec or ctx.source_duration_sec
            tr = await _step(session_id, "trim_video", "trim_video",
                             youtube.trim_video, session_id, clip_start, clip_end)
            ctx.source_duration_sec = float(tr["duration_sec"])

        ea = await _step(session_id, "extract_audio", "extract_audio",
                         youtube.extract_audio, session_id)
        ctx.source_audio_path = ea["path"]

        tr = await _step(session_id, "transcribe", "transcribe",
                         transcribe.transcribe, session_id, sess.youtube_url,
                         sess.clip_start_sec, sess.clip_end_sec)
        ctx.transcript_path = tr["path"]
        transcript = json.loads(Path(ctx.transcript_path).read_text())

        # On resume, repopulate the asset registry so the agent's plan still validates.
        _seed_assets_from_step_results(ctx)

        # Agent loop
        publish(session_id, "step.started", {"name": "agent"})
        agent_result = await run_agent_loop(ctx, transcript)
        publish(session_id, "step.completed", {"name": "agent", "result": agent_result})

        # Assembly
        asm = await _step(session_id, "assemble", "assemble", assemble.assemble, ctx)
        rel = Path(asm["path"]).relative_to(settings.media_root.parent) if asm["path"].startswith(str(settings.media_root.parent)) else Path(asm["path"]).name
        out_rel = str(Path("media") / Path(asm["path"]).relative_to(settings.media_root))
        db.update_session(session_id, status="completed", output_path=out_rel)
        publish(session_id, "session.completed", {"output_path": out_rel})
    except Exception as e:
        log.exception("session %s failed", session_id)
        tb = traceback.format_exc(limit=5)
        db.update_session(session_id, status="failed", failure=str(e))
        publish(session_id, "session.failed", {"error": str(e), "type": type(e).__name__, "trace": tb})
    finally:
        set_session_id(None)

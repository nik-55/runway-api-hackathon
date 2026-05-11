"""ffmpeg assembly. One subprocess invocation, single -filter_complex graph.

Input convention:
- Input 0: source.mp4 (used for any track with `source.type == "original"`)
- Inputs 1..N: each unique asset path, in registration order

Output: 720x1280 30fps h264 mp4.
"""
import asyncio
import json
from pathlib import Path
from typing import Any

from app.agent.context import SessionCtx
from app.logging_setup import get_logger

log = get_logger(__name__)


W, H = 720, 1280
FPS = 30


async def _run(cmd: list[str]) -> tuple[int, str]:
    log.debug("ffmpeg: %s", " ".join(cmd[:8]) + (f" ... ({len(cmd)} args)" if len(cmd) > 8 else ""))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    return proc.returncode or 0, stderr.decode("utf-8", "replace")


def _track_video_filter(track: dict, in_idx: int, idx: int) -> tuple[str, str]:
    """Build the filter chain for a track's video stream.

    Returns (chain_str, output_label).
    """
    label_in = f"{in_idx}:v"
    label_out = f"v{idx}"
    src = track["source"]
    reel_dur = float(track["reel_end"] - track["reel_start"])

    if src["type"] == "original":
        start = float(src["start_sec"])
        end = float(src["end_sec"])
        # trim from original timestamps, reset PTS, then scale/pad to 720x1280
        chain = (
            f"[{label_in}]"
            f"trim=start={start}:end={end},setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={FPS},"
            f"tpad=stop_mode=clone:stop_duration={reel_dur},"
            f"trim=duration={reel_dur},setpts=PTS-STARTPTS"
            f"[{label_out}]"
        )
    else:
        # asset: image is read as a video (with -loop 1) or video clip.
        # Optional start_sec/end_sec carves a sub-window out of the asset so a
        # single long asset can be reused across multiple tracks.
        s = src.get("start_sec")
        e = src.get("end_sec")
        if s is not None and e is not None:
            trim_prefix = f"trim=start={float(s)}:end={float(e)},setpts=PTS-STARTPTS,"
        else:
            trim_prefix = ""
        chain = (
            f"[{label_in}]"
            f"{trim_prefix}"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={FPS},"
            f"tpad=stop_mode=clone:stop_duration={reel_dur},"
            f"trim=duration={reel_dur},setpts=PTS-STARTPTS"
            f"[{label_out}]"
        )
    return chain, label_out


def _track_audio_filter(track: dict, original_in: int, isolated_in: int | None, idx: int) -> tuple[str, str]:
    """Audio chain for a track.

    audio modes:
      "off"                 -> silence
      "original"            -> from input 0 (source.mp4) trimmed to the source window
      "isolated:<asset_id>" -> from a specific isolated asset
      "asset"               -> from the same asset input (for asset-source tracks)
    """
    label_out = f"a{idx}"
    reel_dur = float(track["reel_end"] - track["reel_start"])
    audio_mode = track.get("audio", "off")
    src = track["source"]

    if audio_mode == "off":
        return (
            f"anullsrc=r=44100:cl=stereo,atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{label_out}]",
            label_out,
        )
    if audio_mode == "original" and src["type"] == "original":
        s = float(src["start_sec"])
        e = float(src["end_sec"])
        return (
            f"[{original_in}:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,"
            f"apad,atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{label_out}]",
            label_out,
        )
    if audio_mode.startswith("isolated:") and isolated_in is not None:
        return (
            f"[{isolated_in}:a]asetpts=PTS-STARTPTS,"
            f"apad,atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{label_out}]",
            label_out,
        )
    if audio_mode == "asset" and src["type"] == "asset":
        # asset audio comes from the same input as the track video
        return (
            f"[a_asset_{idx}]atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{label_out}]",
            label_out,
        )
    # fallback: silence
    return (
        f"anullsrc=r=44100:cl=stereo,atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{label_out}]",
        label_out,
    )


def _position_xy(position: str, scale: float) -> tuple[str, str]:
    sw = int(W * scale)
    pad = 24
    if position == "bottom-right":
        return (f"main_w-{sw}-{pad}", f"main_h-overlay_h-{pad}")
    if position == "bottom-left":
        return (f"{pad}", f"main_h-overlay_h-{pad}")
    if position == "top-right":
        return (f"main_w-{sw}-{pad}", f"{pad}")
    if position == "top-left":
        return (f"{pad}", f"{pad}")
    if position == "center":
        return ("(main_w-overlay_w)/2", "(main_h-overlay_h)/2")
    return (f"main_w-{sw}-{pad}", f"main_h-overlay_h-{pad}")


async def assemble(ctx: SessionCtx) -> dict:
    plan_path = ctx.session_dir / "plan.json"
    plan = json.loads(plan_path.read_text())
    out_path = ctx.session_dir / "reel.mp4"

    # ---- decide which assets we need as inputs ----
    track_assets: list[str] = []        # asset_ids referenced by track sources, in order
    overlay_assets: list[str] = []
    audio_assets: list[str] = []        # isolated tracks + audio overlays

    for t in plan["tracks"]:
        if t["source"]["type"] == "asset":
            track_assets.append(t["source"]["asset_id"])
        if isinstance(t.get("audio"), str) and t["audio"].startswith("isolated:"):
            ref = t["audio"].split(":", 1)[1]
            if ref not in audio_assets:
                audio_assets.append(ref)
    for o in plan.get("overlays", []):
        if o["asset_id"] not in overlay_assets:
            overlay_assets.append(o["asset_id"])
    for ao in plan.get("audio_overlays", []):
        if ao["asset_id"] not in audio_assets:
            audio_assets.append(ao["asset_id"])

    # ---- assemble inputs list ----
    inputs: list[list[str]] = []
    inputs.append(["-i", ctx.source_video_path])  # input 0
    track_input_idx: dict[int, int] = {}  # track index -> ffmpeg input idx
    overlay_input_idx: dict[str, int] = {}
    audio_input_idx: dict[str, int] = {}

    next_idx = 1
    # track-source asset inputs (one per track to keep filter chains simple)
    for ti, t in enumerate(plan["tracks"]):
        if t["source"]["type"] == "asset":
            asset_id = t["source"]["asset_id"]
            asset = ctx.assets.get(asset_id)
            if not asset:
                raise RuntimeError(f"missing asset {asset_id}")
            path = asset["path"]
            kind = asset["kind"]
            if kind == "image":
                # static image, loop until trimmed
                inputs.append(["-loop", "1", "-t", str(float(t["reel_end"] - t["reel_start"]) + 1.0), "-i", path])
            else:
                inputs.append(["-i", path])
            track_input_idx[ti] = next_idx
            next_idx += 1

    for asset_id in overlay_assets:
        if asset_id in track_input_idx.values():
            # already added as a track source — re-use? simpler: add a separate input
            pass
        asset = ctx.assets.get(asset_id)
        if not asset:
            raise RuntimeError(f"missing overlay asset {asset_id}")
        path = asset["path"]
        kind = asset["kind"]
        if kind == "image":
            inputs.append(["-loop", "1", "-i", path])
        else:
            inputs.append(["-i", path])
        overlay_input_idx[asset_id] = next_idx
        next_idx += 1

    for asset_id in audio_assets:
        asset = ctx.assets.get(asset_id)
        if not asset:
            raise RuntimeError(f"missing audio asset {asset_id}")
        inputs.append(["-i", asset["path"]])
        audio_input_idx[asset_id] = next_idx
        next_idx += 1

    # ---- build filter graph ----
    filters: list[str] = []
    track_video_labels: list[str] = []
    track_audio_labels: list[str] = []

    for ti, t in enumerate(plan["tracks"]):
        in_idx = track_input_idx.get(ti, 0)  # 0 = source
        chain, label = _track_video_filter(t, in_idx, ti)
        filters.append(chain)
        track_video_labels.append(label)

        # audio
        audio_mode = t.get("audio", "off")
        reel_dur = float(t["reel_end"] - t["reel_start"])
        a_label = f"a{ti}"
        if audio_mode == "off":
            filters.append(
                f"anullsrc=r=44100:cl=stereo:d={reel_dur}[{a_label}]"
            )
        elif audio_mode == "original" and t["source"]["type"] == "original":
            s = float(t["source"]["start_sec"]); e = float(t["source"]["end_sec"])
            filters.append(
                f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,"
                f"apad,atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{a_label}]"
            )
        elif audio_mode.startswith("isolated:"):
            ref = audio_mode.split(":", 1)[1]
            ai = audio_input_idx.get(ref)
            if ai is None:
                filters.append(f"anullsrc=r=44100:cl=stereo:d={reel_dur}[{a_label}]")
            else:
                filters.append(
                    f"[{ai}:a]asetpts=PTS-STARTPTS,apad,"
                    f"atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{a_label}]"
                )
        elif audio_mode == "asset" and t["source"]["type"] == "asset":
            asset_id = t["source"]["asset_id"]
            asset = ctx.assets.get(asset_id) or {}
            if asset.get("kind") == "video":
                s = t["source"].get("start_sec")
                e = t["source"].get("end_sec")
                if s is not None and e is not None:
                    atrim_prefix = f"atrim=start={float(s)}:end={float(e)},"
                else:
                    atrim_prefix = ""
                filters.append(
                    f"[{in_idx}:a]{atrim_prefix}asetpts=PTS-STARTPTS,apad,"
                    f"atrim=duration={reel_dur},asetpts=PTS-STARTPTS[{a_label}]"
                )
            else:
                filters.append(f"anullsrc=r=44100:cl=stereo:d={reel_dur}[{a_label}]")
        else:
            filters.append(f"anullsrc=r=44100:cl=stereo:d={reel_dur}[{a_label}]")
        track_audio_labels.append(a_label)

    # concat tracks. ffmpeg requires interleaved (v0,a0,v1,a1,...) when v=1:a=1.
    concat_inputs = "".join(
        f"[{v}][{a}]" for v, a in zip(track_video_labels, track_audio_labels)
    )
    n_tracks = len(track_video_labels)
    filters.append(f"{concat_inputs}concat=n={n_tracks}:v=1:a=1[basev][basea]")

    # apply video overlays
    current = "basev"
    for oi, o in enumerate(plan.get("overlays", [])):
        asset_id = o["asset_id"]
        in_idx = overlay_input_idx[asset_id]
        scale = float(o.get("scale", 0.28))
        ov_label = f"ov{oi}"
        sw = int(W * scale)
        filters.append(
            f"[{in_idx}:v]scale={sw}:-2,fps={FPS},setsar=1[{ov_label}]"
        )
        x, y = _position_xy(o.get("position", "bottom-right"), scale)
        rs = float(o["reel_start"]); re = float(o["reel_end"])
        next_label = f"ovd{oi}"
        filters.append(
            f"[{current}][{ov_label}]overlay=x={x}:y={y}:enable='between(t,{rs},{re})'[{next_label}]"
        )
        current = next_label
    final_video_label = current

    # mix audio overlays into base audio
    final_audio_label = "basea"
    audio_overlay_specs = plan.get("audio_overlays", [])
    if audio_overlay_specs:
        mix_inputs = ["[basea]"]
        for ai, ao in enumerate(audio_overlay_specs):
            asset_id = ao["asset_id"]
            in_idx = audio_input_idx[asset_id]
            rs = float(ao["reel_start"]); re = float(ao["reel_end"])
            gain = float(ao.get("gain_db", 0.0))
            label = f"aov{ai}"
            filters.append(
                f"[{in_idx}:a]volume={gain:.2f}dB,"
                f"adelay={int(rs*1000)}|{int(rs*1000)},"
                f"atrim=end={re},asetpts=PTS-STARTPTS[{label}]"
            )
            mix_inputs.append(f"[{label}]")
        filters.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[finala]"
        )
        final_audio_label = "finala"

    # build command
    cmd: list[str] = ["ffmpeg", "-y"]
    for inp in inputs:
        cmd.extend(inp)
    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", f"[{final_video_label}]",
        "-map", f"[{final_audio_label}]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS),
        "-t", f"{float(plan['duration_sec']):.3f}",
        "-movflags", "+faststart",
        str(out_path),
    ])

    rc, stderr = await _run(cmd)
    if rc != 0:
        log.error("ffmpeg assembly failed:\n%s", stderr[-2000:])
        raise RuntimeError(f"ffmpeg assembly failed: {stderr[-400:]}")

    return {"path": str(out_path)}

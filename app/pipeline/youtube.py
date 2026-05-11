import asyncio
import shutil
import sys
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)

_COOKIES = Path(__file__).parents[2] / "cookies_yt.txt"
YT_DLP = (
    [sys.executable, "-m", "yt_dlp", "--cookies", str(_COOKIES)]
    if _COOKIES.exists()
    else [sys.executable, "-m", "yt_dlp"]
)


async def _run(cmd: list[str]) -> tuple[int, str, str]:
    log.debug("subprocess: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


@retry(stop=stop_after_attempt(2), wait=wait_exponential_jitter(initial=1, max=10), reraise=True)
async def download_video(session_id: str, youtube_url: str) -> dict:
    """Download a single MP4 (≤720p) into media/sessions/<id>/source.mp4.

    Returns metadata: {"path": str, "duration_sec": float, "title": str}.
    Raises ValueError if duration exceeds MAX_VIDEO_DURATION_SEC.
    """
    out_dir = settings.session_dir(session_id)
    out_path = out_dir / "source.mp4"

    # First fetch metadata to enforce length cap before bothering with the download
    rc, stdout, stderr = await _run(
        YT_DLP + ["--no-warnings", "-J", "--skip-download", youtube_url]
    )
    if rc != 0:
        raise RuntimeError(f"yt-dlp metadata failed: {stderr.strip()[-400:]}")
    import json
    info = json.loads(stdout)
    duration = float(info.get("duration") or 0)
    title = info.get("title") or ""
    if duration > settings.max_video_duration_sec:
        raise ValueError(
            f"Video too long: {duration:.0f}s > {settings.max_video_duration_sec}s"
        )

    rc, _, stderr = await _run(
        YT_DLP + [
            "--no-warnings", "--no-playlist",
            "-f", "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/b",
            "--merge-output-format", "mp4",
            "-o", str(out_path),
            youtube_url,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"yt-dlp download failed: {stderr.strip()[-400:]}")

    if not out_path.exists():
        # Sometimes yt-dlp writes a different extension; find it
        candidates = list(out_dir.glob("source.*"))
        if not candidates:
            raise RuntimeError("yt-dlp produced no source file")
        actual = candidates[0]
        if actual.suffix != ".mp4":
            shutil.move(str(actual), str(out_path))

    return {"path": str(out_path), "duration_sec": duration, "title": title}


async def trim_video(session_id: str, start_sec: float, end_sec: float) -> dict:
    """Trim source.mp4 in-place to [start_sec, end_sec].

    Re-encodes (not stream copy) so the output has frame-accurate cuts and
    timestamps reset to 0 — downstream tools (transcribe, get_frames,
    isolate_voice) reference timestamps relative to the trimmed file.
    """
    out_dir = settings.session_dir(session_id)
    src = out_dir / "source.mp4"
    tmp = out_dir / "source_trim.mp4"
    rc, _, stderr = await _run([
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(tmp),
    ])
    if rc != 0:
        raise RuntimeError(f"ffmpeg trim_video failed: {stderr.strip()[-400:]}")
    tmp.replace(src)
    duration = await ffprobe_duration(src)
    return {"path": str(src), "duration_sec": duration}


async def extract_audio(session_id: str) -> dict:
    """Extract audio (m4a) from the downloaded video for transcription."""
    out_dir = settings.session_dir(session_id)
    src = out_dir / "source.mp4"
    out = out_dir / "source.m4a"

    rc, _, stderr = await _run([
        "ffmpeg", "-y", "-i", str(src),
        "-vn", "-c:a", "aac", "-b:a", "128k",
        str(out),
    ])
    if rc != 0:
        raise RuntimeError(f"ffmpeg extract_audio failed: {stderr.strip()[-400:]}")
    return {"path": str(out)}


async def to_flac(audio_path: Path | str, out_path: Path | str) -> str:
    """Convert any audio file to FLAC for HF Whisper."""
    rc, _, stderr = await _run([
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ac", "1", "-ar", "16000", "-c:a", "flac",
        str(out_path),
    ])
    if rc != 0:
        raise RuntimeError(f"ffmpeg flac convert failed: {stderr.strip()[-400:]}")
    return str(out_path)


async def ffprobe_duration(path: str | Path) -> float:
    rc, stdout, stderr = await _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    if rc != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.strip()[-400:]}")
    return float(stdout.strip() or 0.0)


async def slice_audio(src: str | Path, start_sec: float, end_sec: float, out_path: str | Path) -> str:
    rc, _, stderr = await _run([
        "ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}",
        "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "192k", str(out_path),
    ])
    if rc != 0:
        raise RuntimeError(f"ffmpeg slice_audio failed: {stderr.strip()[-400:]}")
    return str(out_path)


async def extract_frames(
    src: str | Path, start_sec: float, end_sec: float, count: int, out_pattern: str | Path
) -> list[str]:
    """Sample `count` frames evenly across [start, end]. Returns sorted file paths."""
    duration = max(0.001, float(end_sec) - float(start_sec))
    fps = max(0.5, float(count) / duration)
    rc, _, stderr = await _run([
        "ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-to", f"{end_sec:.3f}",
        "-i", str(src),
        "-vf", f"fps={fps},scale=512:-1",
        "-frames:v", str(count),
        str(out_pattern),
    ])
    if rc != 0:
        raise RuntimeError(f"ffmpeg extract_frames failed: {stderr.strip()[-400:]}")
    base = Path(str(out_pattern)).parent
    stem_glob = Path(str(out_pattern)).name.replace("%03d", "*").replace("%d", "*")
    files = sorted(base.glob(stem_glob))
    return [str(p) for p in files]

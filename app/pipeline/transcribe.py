import asyncio
import json
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app import db
from app.config import settings
from app.logging_setup import get_logger
from app.pipeline.youtube import to_flac

log = get_logger(__name__)


# HF Whisper inference endpoint. The router exposes Whisper variants under
# /hf-inference/models/<model>. We use the "turbo" variant by default and ask
# for word-level timestamps. If the provider doesn't honour the parameter
# we still get a usable transcript.

def _model_path(model_id: str) -> str:
    # STT_MODEL like "openai/whisper-large-v3-turbo:fastest" — strip provider tag
    return model_id.split(":")[0]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=20),
    reraise=True,
)
def _post_audio(flac_path: str, model_id: str, token: str) -> dict:
    url = f"https://router.huggingface.co/hf-inference/models/{_model_path(model_id)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "audio/flac",
    }
    params = {"return_timestamps": "word"}
    log.debug("POST %s params=%s", url, params)
    with open(flac_path, "rb") as f:
        resp = requests.post(url, headers=headers, params=params, data=f, timeout=600)
    if resp.status_code >= 500 or resp.status_code == 429:
        log.warning("whisper transient %s: %s", resp.status_code, resp.text[:200])
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise RuntimeError(f"Whisper {resp.status_code}: {resp.text[:400]}")
    return resp.json()


async def transcribe(
    session_id: str,
    youtube_url: str,
    clip_start_sec: float | None,
    clip_end_sec: float | None,
) -> dict:
    """Transcribe session source audio. Writes transcript.json with text + (optional) word timestamps.

    Consults a global cache keyed by (youtube_url, clip_start_sec, clip_end_sec) before
    calling Whisper — Whisper inference dominates pipeline latency, and re-running with
    the same input is common during iteration.
    """
    sd = settings.session_dir(session_id)
    out = sd / "transcript.json"

    cached = db.get_cached_transcript(youtube_url, clip_start_sec, clip_end_sec)
    if cached is not None:
        out.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
        words = cached.get("words") or []
        text = cached.get("text") or ""
        log.info("transcript cache hit: %d words, %d chars", len(words), len(text))
        return {"path": str(out), "word_count": len(words), "char_count": len(text), "cached": True}

    audio_in = sd / "source.m4a"
    flac = sd / "source.flac"
    await to_flac(audio_in, flac)

    token = settings.hf_token or settings.openai_api_key
    if not token:
        raise RuntimeError("HF token missing — set OPENAI_API_KEY or HF_TOKEN in .env")

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, lambda: _post_audio(str(flac), settings.stt_model, token)
    )

    # Normalise into a stable shape regardless of provider variations.
    text = data.get("text", "")
    words: list[dict] = []
    raw_chunks = data.get("chunks") or data.get("words") or []
    for c in raw_chunks:
        ts = c.get("timestamp") or c.get("timestamps") or [None, None]
        if isinstance(ts, list) and len(ts) >= 2:
            start, end = ts[0], ts[1]
        else:
            start = c.get("start"); end = c.get("end")
        words.append({
            "text": (c.get("text") or c.get("word") or "").strip(),
            "start": float(start) if start is not None else None,
            "end": float(end) if end is not None else None,
        })

    transcript = {"text": text.strip(), "words": words, "raw_keys": list(data.keys())}
    out.write_text(json.dumps(transcript, ensure_ascii=False, indent=2))
    db.put_cached_transcript(youtube_url, clip_start_sec, clip_end_sec, transcript)
    log.info("transcript: %d words, %d chars", len(words), len(text))
    return {"path": str(out), "word_count": len(words), "char_count": len(text), "cached": False}

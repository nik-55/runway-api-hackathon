"""Vision sub-call. Architecturally distinct from the orchestrator client even
though both currently point at Kimi K2.6 (multimodal).

Raw images flow ONLY through this module; the orchestrator never sees them."""
import asyncio
import base64
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.config import settings
from app.llm.kimi_client import get_client
from app.logging_setup import get_logger

log = get_logger(__name__)


def _encode_image(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower().lstrip(".")
    if suffix in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif suffix == "png":
        mime = "image/png"
    elif suffix == "webp":
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=15),
    reraise=True,
)
def _ask_vision_sync(prompt: str, image_paths: list[str]) -> str:
    client = get_client()
    content: list[dict] = [{"type": "text", "text": prompt}]
    for ip in image_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": _encode_image(ip)},
        })
    log.debug("vision call: %d images, prompt=%r", len(image_paths), prompt[:100])
    resp = client.chat.completions.create(
        model=settings.vision_model_name,
        messages=[
            {"role": "system", "content": "You are a concise visual analyst. Describe what you see in plain text — no markdown, no headers."},
            {"role": "user", "content": content},
        ],
        max_tokens=400,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


async def ask_vision(prompt: str, image_paths: list[str]) -> str:
    return await asyncio.to_thread(_ask_vision_sync, prompt, image_paths)

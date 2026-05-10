import asyncio
from functools import lru_cache

import requests
from runwayml import RunwayML
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_client() -> RunwayML:
    if not settings.runway_api_key:
        raise RuntimeError("RUNWAY_API_KEY missing")
    return RunwayML(api_key=settings.runway_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=15),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True,
)
def download_to(url: str, out_path: str) -> str:
    log.debug("downloading %s -> %s", url[:80], out_path)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
    return out_path


async def download_to_async(url: str, out_path: str) -> str:
    return await asyncio.to_thread(download_to, url, out_path)

from functools import lru_cache

from openai import OpenAI

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base_url,
    )

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent


# Make .env authoritative over pre-existing shell env vars (e.g. stale OPENAI_API_KEY).
# Hackathon scope: this is a single-user dev project.
def _load_dotenv_override() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    import os
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if v:
            os.environ[k] = v


_load_dotenv_override()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runway_api_key: str = ""
    openai_api_key: str = ""
    openai_api_base_url: str = "https://router.huggingface.co/v1"
    openai_model_name: str = "moonshotai/Kimi-K2.6:fireworks-ai"
    vision_model_name: str = "moonshotai/Kimi-K2.6:fireworks-ai"
    stt_model: str = "openai/whisper-large-v3-turbo:fastest"
    hf_token: str = ""

    character_avatar_preset: str = "96af6db1-6e10-40da-b10d-8e712a826111"
    character_voice_preset: str = "morgan"

    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    max_agent_turns: int = 25
    max_completion_tokens: int = 32768
    max_video_duration_sec: int = 600
    min_reel_duration_sec: float = 10.0
    max_reel_duration_sec: float = 60.0

    media_root: Path = REPO_ROOT / "media"
    logs_root: Path = REPO_ROOT / "logs"
    data_root: Path = REPO_ROOT / "data"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        if not self.hf_token:
            self.hf_token = self.openai_api_key

    @property
    def db_path(self) -> Path:
        return self.data_root / "reelagent.sqlite"

    def session_dir(self, session_id: str) -> Path:
        d = self.media_root / "sessions" / session_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "tools").mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()

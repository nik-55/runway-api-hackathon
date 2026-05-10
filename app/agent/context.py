from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings


@dataclass
class SessionCtx:
    session_id: str
    direction: str | None = None
    transcript_path: str = ""
    source_video_path: str = ""
    source_audio_path: str = ""
    source_duration_sec: float = 0.0
    # asset registry: asset_id -> {"kind": "image|video|audio", "path": str, "duration_sec": float|None, "tool": str}
    assets: dict[str, dict] = field(default_factory=dict)

    @property
    def session_dir(self) -> Path:
        return settings.session_dir(self.session_id)

    @property
    def tools_dir(self) -> Path:
        return self.session_dir / "tools"

    def register_asset(self, asset_id: str, kind: str, path: str, duration_sec: float | None, tool: str) -> None:
        self.assets[asset_id] = {
            "kind": kind,
            "path": path,
            "duration_sec": duration_sec,
            "tool": tool,
        }

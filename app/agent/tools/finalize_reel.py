import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agent.context import SessionCtx
from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)

REEL_RATIO = "720:1280"
EPS = 0.05  # max gap/overlap between adjacent tracks


def _reel_duration() -> float:
    return settings.reel_duration_sec


def _min_reel_duration() -> float:
    return settings.min_reel_duration_sec


def _max_reel_duration() -> float:
    return settings.max_reel_duration_sec


class Moment(BaseModel):
    start_sec: float
    end_sec: float
    why: str = ""


class TrackSourceOriginal(BaseModel):
    type: Literal["original"]
    start_sec: float
    end_sec: float


class TrackSourceAsset(BaseModel):
    type: Literal["asset"]
    asset_id: str


class Track(BaseModel):
    kind: Literal["video"]
    source: TrackSourceOriginal | TrackSourceAsset
    reel_start: float
    reel_end: float
    audio: str = "off"  # "original" | "off" | f"isolated:<asset_id>" | "asset"


class Overlay(BaseModel):
    asset_id: str
    reel_start: float
    reel_end: float
    position: str = "bottom-right"
    scale: float = 0.28


class AudioOverlay(BaseModel):
    asset_id: str
    reel_start: float
    reel_end: float
    gain_db: float = 0.0


class ReelPlan(BaseModel):
    duration_sec: float = Field(default_factory=_reel_duration)
    ratio: str = Field(default=REEL_RATIO)
    moment: Moment
    commentary_script: str = ""
    tracks: list[Track]
    overlays: list[Overlay] = Field(default_factory=list)
    audio_overlays: list[AudioOverlay] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_basics(self):
        if self.duration_sec < _min_reel_duration() - EPS:
            raise ValueError(f"duration_sec must be at least {_min_reel_duration()}")
        if self.duration_sec > _max_reel_duration() + EPS:
            raise ValueError(f"duration_sec must not exceed {_max_reel_duration()}")
        return self


def _validate_against_assets(plan: ReelPlan, assets: dict[str, dict]) -> list[str]:
    issues: list[str] = []

    for i, t in enumerate(plan.tracks):
        if t.reel_end <= t.reel_start:
            issues.append(f"track[{i}]: reel_end must be > reel_start")
        if isinstance(t.source, TrackSourceAsset):
            if t.source.asset_id not in assets:
                issues.append(f"track[{i}]: unknown asset_id {t.source.asset_id}")
        if t.audio.startswith("isolated:"):
            ref = t.audio.split(":", 1)[1]
            if ref not in assets:
                issues.append(f"track[{i}]: audio refers to unknown asset_id {ref}")

    # tile [0, plan.duration_sec] with no gap or overlap
    sorted_tracks = sorted(plan.tracks, key=lambda x: x.reel_start)
    cursor = 0.0
    for i, t in enumerate(sorted_tracks):
        if abs(t.reel_start - cursor) > EPS:
            issues.append(
                f"track {i}: gap or overlap at reel_start={t.reel_start} (expected {cursor:.3f})"
            )
        cursor = t.reel_end
    tol = settings.reel_duration_tolerance_sec
    if abs(cursor - plan.duration_sec) > tol:
        issues.append(f"tracks must end within {tol}s of {plan.duration_sec}, ended at {cursor:.3f}")

    for i, o in enumerate(plan.overlays):
        if o.asset_id not in assets:
            issues.append(f"overlay[{i}]: unknown asset_id {o.asset_id}")
        if o.reel_end <= o.reel_start:
            issues.append(f"overlay[{i}]: reel_end must be > reel_start")

    for i, ao in enumerate(plan.audio_overlays):
        if ao.asset_id not in assets:
            issues.append(f"audio_overlay[{i}]: unknown asset_id {ao.asset_id}")
        if ao.reel_end <= ao.reel_start:
            issues.append(f"audio_overlay[{i}]: reel_end must be > reel_start")

    if plan.moment.end_sec - plan.moment.start_sec > _max_reel_duration() + EPS:
        issues.append(f"moment span longer than {_max_reel_duration()}s")

    has_character = any(
        a.get("tool") == "generate_character_video" for a in assets.values()
    )
    if not has_character:
        issues.append(
            "you have not called generate_character_video yet — the commentary track is mandatory"
        )

    return issues


async def call(ctx: SessionCtx, *, plan: dict) -> dict:
    try:
        parsed = ReelPlan.model_validate(plan)
    except ValidationError as e:
        return {"error": "schema validation failed", "issues": [str(err) for err in e.errors()]}

    issues = _validate_against_assets(parsed, ctx.assets)
    if issues:
        return {"error": "plan invalid", "issues": issues}

    out = ctx.session_dir / "plan.json"
    out.write_text(parsed.model_dump_json(indent=2))
    log.info("plan finalized for session %s", ctx.session_id)
    return {"ok": True, "plan_path": str(out)}

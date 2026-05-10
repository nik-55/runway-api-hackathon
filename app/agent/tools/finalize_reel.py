import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.agent.context import SessionCtx
from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)

REEL_RATIO = "720:1280"
EPS = 0.05  # max gap/overlap between adjacent tracks


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
    ratio: str = Field(default=REEL_RATIO)
    moment: Moment
    commentary_script: str = ""
    tracks: list[Track]
    overlays: list[Overlay] = Field(default_factory=list)
    audio_overlays: list[AudioOverlay] = Field(default_factory=list)


def _validate_against_assets(plan: ReelPlan, assets: dict[str, dict]) -> tuple[list[str], float]:
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

    # tracks must tile [0, total] with no gap or overlap; total is derived from the last reel_end
    sorted_tracks = sorted(plan.tracks, key=lambda x: x.reel_start)
    cursor = 0.0
    for i, t in enumerate(sorted_tracks):
        if abs(t.reel_start - cursor) > EPS:
            issues.append(
                f"track {i}: gap or overlap at reel_start={t.reel_start} (expected {cursor:.3f})"
            )
        cursor = t.reel_end
    total = cursor

    if total < _min_reel_duration() - EPS:
        issues.append(f"reel total {total:.3f}s is below minimum {_min_reel_duration()}s")
    if total > _max_reel_duration() + EPS:
        issues.append(f"reel total {total:.3f}s exceeds maximum {_max_reel_duration()}s")

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

    # video overlays are silent unless paired with an audio_overlays entry
    for i, o in enumerate(plan.overlays):
        asset = assets.get(o.asset_id)
        if not asset or asset.get("kind") != "video":
            continue
        paired = any(
            ao.asset_id == o.asset_id
            and ao.reel_start <= o.reel_start + EPS
            and ao.reel_end >= o.reel_end - EPS
            for ao in plan.audio_overlays
        )
        if not paired:
            log.info(
                "overlay[%d] (asset %s) has no matching audio_overlays entry — will play silently if unintended",
                i, o.asset_id,
            )

    if plan.moment.end_sec - plan.moment.start_sec > _max_reel_duration() + EPS:
        issues.append(f"moment span longer than {_max_reel_duration()}s")

    has_character = any(
        a.get("tool") == "generate_character_video" for a in assets.values()
    )
    if not has_character:
        issues.append(
            "you have not called generate_character_video yet — the commentary track is mandatory"
        )

    return issues, total


async def call(ctx: SessionCtx, *, plan: dict) -> dict:
    try:
        parsed = ReelPlan.model_validate(plan)
    except ValidationError as e:
        return {"error": "schema validation failed", "issues": [str(err) for err in e.errors()]}

    issues, total = _validate_against_assets(parsed, ctx.assets)
    if issues:
        return {"error": "plan invalid", "issues": issues}

    out = ctx.session_dir / "plan.json"
    payload = parsed.model_dump()
    payload["duration_sec"] = round(total, 3)
    out.write_text(json.dumps(payload, indent=2))
    log.info("plan finalized for session %s (duration=%.3fs)", ctx.session_id, total)
    return {"ok": True, "plan_path": str(out)}

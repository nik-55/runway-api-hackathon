"""Tool registry. Each tool is `async def call(ctx, **kwargs) -> dict`.

The orchestrator sees `TOOL_SCHEMAS` (OpenAI tool-calling JSON schemas).
`finalize_reel` is included — calling it ends the loop.
"""
from typing import Any, Awaitable, Callable

from app.agent.tools import (
    finalize_reel,
    generate_animated_reaction,
    generate_character_video,
    generate_reaction_image,
    generate_sound_effect,
    get_frames,
    isolate_voice,
    update_plan,
)
from app.config import settings


ToolFn = Callable[..., Awaitable[dict]]


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": (
                "Write or revise your working plan as freeform text. This is your scratchpad — "
                "the model has no other durable memory across turns, so anything you don't capture "
                "here is forgotten once you call your next tool. Use it to record: the moment you "
                "picked, the take/angle, which beats land where, what assets you still need, and "
                "why. Call this in PARALLEL with other tools whenever your strategy changes. "
                "MUST be called on your first turn alongside any other tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "string",
                        "description": "Current plan as plain text. Replaces any prior plan in your working memory.",
                    },
                },
                "required": ["plan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_frames",
            "description": (
                "Sample frames from the source video at [start_sec, end_sec], pass them to a vision "
                "model with your prompt, and return a TEXT answer. Use when the transcript is "
                "ambiguous and you need to know what is on screen. Cheap (local + one LLM call). "
                "Returns text only — raw images never reach you."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_sec": {"type": "number", "description": "Start of window in source seconds."},
                    "end_sec":   {"type": "number", "description": "End of window in source seconds."},
                    "prompt":    {"type": "string", "description": "Concrete question to ask about the frames."},
                },
                "required": ["start_sec", "end_sec", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_reaction_image",
            "description": (
                "Generate a still meme/reaction image via Runway gen4_image. Returns an asset_id "
                "you can reference in the final reel plan. 9:16 vertical only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_animated_reaction",
            "description": (
                "Generate a short text-to-video reaction beat via Runway gen4.5. Use when motion lands "
                "harder than a still. duration must be one of [4, 6, 8] seconds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt":   {"type": "string"},
                    "duration": {"type": "integer", "enum": [4, 6, 8]},
                },
                "required": ["prompt", "duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sound_effect",
            "description": "Generate a short SFX via Runway eleven_text_to_sound_v2. duration in seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt":   {"type": "string"},
                    "duration": {"type": "number", "description": "Length in seconds (0.5 to 22)."},
                },
                "required": ["prompt", "duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_character_video",
            "description": (
                "Generate a lip-synced avatar video of the commentary script via Runway avatar_videos. "
                "The script may include emotion markers like [shocked], [laughing], [disbelief], "
                "[serious], [sarcastic], [excited], [deadpan], [pause]. You MUST call this exactly once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script":       {"type": "string"},
                    "voice_preset": {"type": "string", "description": "Optional Runway voice preset id (default: ruby)."},
                },
                "required": ["script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isolate_voice",
            "description": (
                "Isolate cleaned voice from the source audio between [start_sec, end_sec]. Returns an "
                "asset_id you can use as the audio track for any cut from the original video."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_sec": {"type": "number"},
                    "end_sec":   {"type": "number"},
                },
                "required": ["start_sec", "end_sec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_reel",
            "description": (
                f"Submit the final assembly plan and end the session. The plan must tile from 0 with no "
                f"gaps; the total length must land within [{settings.min_reel_duration_sec:g}, "
                f"{settings.max_reel_duration_sec:g}] seconds. Reference only existing asset_ids, and "
                f"follow the schema in the system prompt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {"type": "object"},
                },
                "required": ["plan"],
            },
        },
    },
]


TOOL_REGISTRY: dict[str, ToolFn] = {
    "update_plan": update_plan.call,
    "get_frames": get_frames.call,
    "generate_reaction_image": generate_reaction_image.call,
    "generate_animated_reaction": generate_animated_reaction.call,
    "generate_sound_effect": generate_sound_effect.call,
    "generate_character_video": generate_character_video.call,
    "isolate_voice": isolate_voice.call,
    "finalize_reel": finalize_reel.call,
}

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**ReelAgent** — paste a YouTube URL, get an AI reaction reel (10–60 s) with a lip-synced character commentator. A single Kimi K2.6 agent autonomously decides what moment to clip, writes commentary, calls Runway APIs for media assets, and assembles the final video.

## Commands

```bash
# Run locally (dev)
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Run with Docker
docker compose up --build

# Install dependencies
pip install -r requirements.txt
```

No test suite or linter currently configured.

## Architecture

### Request lifecycle

`POST /sessions` → inserts DB row → `asyncio.create_task(runner.run(session_id))` → redirects to `/sessions/{id}`. The browser subscribes to `GET /sessions/{id}/events` (SSE) for live progress. Everything happens in one process using `asyncio`.

### Pipeline stages (`app/pipeline/runner.py`)

1. **Pre-agent (deterministic, checkpointed):**
   - `youtube.download_video` — yt-dlp downloads full video (not audio-only, because `get_frames` needs the video file)
   - `youtube.extract_audio` — ffmpeg extracts `.m4a` from the video
   - `transcribe.transcribe` — HF Whisper via raw HTTP (not OpenAI-compatible), returns word-level timestamps

2. **Agent loop (`app/agent/loop.py`):** Kimi K2.6 via HF router (OpenAI-compatible), runs up to `MAX_AGENT_TURNS` turns. All tool calls in a single turn run in parallel via `asyncio.gather`. Loop ends when the model calls `finalize_reel` with a valid plan.

3. **Assembly (`app/pipeline/assemble.py`):** pure ffmpeg, driven by the plan JSON the agent produced. No Runway calls here.

### The orchestrator design (critical invariant)

The agent is the sole decision-maker — there is no fixed pipeline of "find moment → write commentary → assemble." The model decides which tools to call, in what order, with what prompts.

**The model never sees raw images.** `get_frames` runs a vision sub-call internally (`app/llm/vision_client.py`) and returns `{"answer": "<text>"}` only. Raw frames never enter the orchestrator's `messages` list.

### Tools (`app/agent/tools/`)

Each tool is `async def call(ctx: SessionCtx, **kwargs) -> dict`. All tool schemas are in `app/agent/tools/__init__.py:TOOL_SCHEMAS` (OpenAI format).

| Tool | Backend | What it returns |
|---|---|---|
| `get_frames` | ffmpeg + Kimi vision sub-call | `{"answer": str}` — text only |
| `generate_reaction_image` | Runway `gen4_image_turbo` | `{"asset_id": str}` |
| `generate_animated_reaction` | Runway `gen4.5` | `{"asset_id": str, "duration_sec": int}` |
| `generate_sound_effect` | Runway `eleven_text_to_sound_v2` | `{"asset_id": str, "duration_sec": int}` |
| `generate_character_video` | Runway `gwm1_avatars` (avatar_videos) | `{"asset_id": str, "duration_sec": float}` |
| `isolate_voice` | ffmpeg slice + Runway `eleven_voice_isolation` | `{"asset_id": str, "duration_sec": float}` |
| `finalize_reel` | pydantic validation + writes plan.json | signals loop exit |

Generated assets are saved under `media/sessions/<session_id>/tools/` with filenames `<type>_<asset_id>.<ext>`. The `SessionCtx.assets` dict maps `asset_id → {kind, path, duration_sec, tool}`.

### Checkpointing / resumption (`app/pipeline/checkpoints.py`)

Every expensive operation goes through `checkpointed(session_id, step_key, fn, ...)`. On the first run it executes and writes to `step_results` table. On retry/resume it returns the cached result without re-calling Runway or HF. Step keys: `"download_video"`, `"extract_audio"`, `"transcribe"`, `"assemble"` for pre-agent steps; `"tool:<turn>:<call_id>"` for tool calls.

`POST /sessions/{id}/resume` re-runs the runner; `_seed_assets_from_step_results` replays completed tool results back into `ctx.assets` so plan validation still works.

### Events / SSE (`app/pipeline/events.py`)

`publish(session_id, type, payload)` writes to the `events` table and fans out to all active `asyncio.Queue` subscribers. `GET /sessions/{id}/events` backfills from DB then subscribes live. Heartbeat comment every 15s keeps proxies from dropping the connection.

### Database (`app/db.py`)

SQLite, stdlib `sqlite3`, no ORM. Three tables: `sessions`, `events` (append-only, drives SSE and UI history), `step_results` (resumption cache).

### LLM clients (`app/llm/`)

- `kimi_client.py` — `openai.OpenAI` pointed at `OPENAI_API_BASE_URL` (HF router). Used by the orchestrator loop. Wrapped in `tenacity` retry (4 attempts, exponential jitter) for `RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`.
- `vision_client.py` — same endpoint, same model, but a separate client used only inside `get_frames`. Sends base64 image data URIs in a one-shot user message.

### Config (`app/config.py`)

`pydantic-settings` `Settings` singleton. `.env` values **override** shell env (explicit `_load_dotenv_override` before pydantic loads). Copy `.env.sample` to `.env` and fill in keys before running.

Key env vars:
- `RUNWAY_API_KEY` — Runway API key
- `OPENAI_API_KEY` / `HF_TOKEN` — HF token (same value; `HF_TOKEN` falls back to `OPENAI_API_KEY` if unset)
- `OPENAI_API_BASE_URL` — default `https://router.huggingface.co/v1`
- `OPENAI_MODEL_NAME` — default `moonshotai/Kimi-K2.6:fireworks-ai`
- `CHARACTER_AVATAR_PRESET` — Runway preset id (default `influencer`)
- `REEL_DURATION_SEC` — default target reel length (default `30.0`)
- `MIN_REEL_DURATION_SEC` — minimum allowed reel length (default `10.0`)
- `MAX_REEL_DURATION_SEC` — maximum allowed reel length (default `60.0`)
- `REEL_DURATION_TOLERANCE_SEC` — how far tracks may deviate from `duration_sec` before the plan is rejected (default `15.0`). Set generously so the model spends tokens on creative decisions, not fixing frame-precise timing.

### Frontend

Server-rendered Jinja2 HTML (`app/templates/`). No JS framework. The session detail page (`session.html`) uses the browser's native `EventSource` API to consume the SSE stream and renders each event type differently (step checklist, collapsible thinking blocks, tool call/result rows, final video player).

### Tracing

No tracing stack is running by default. Langfuse config keys (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) are accepted by `config.py` but not wired up. The SSE event stream (`GET /sessions/{id}/events`) provides live visibility into every agent step and tool call.

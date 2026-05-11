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

`POST /sessions` (multipart) accepts either a `youtube_url` field **or** a `video_file` upload (must pass one). On upload, the route streams the MP4 to `media/sessions/<id>/source.mp4`, runs `ffprobe_duration` to enforce `MAX_VIDEO_DURATION_SEC`, and stores the URL slot as `upload:<filename>` so downstream code can branch on the prefix. Then: insert DB row → `asyncio.create_task(runner.run(session_id))` → redirect to `/sessions/{id}`. The browser subscribes to `GET /sessions/{id}/events` (SSE) for live progress. Everything happens in one process using `asyncio`.

### Pipeline stages (`app/pipeline/runner.py`)

1. **Pre-agent (deterministic, checkpointed):**
   - `youtube.download_video` — yt-dlp downloads full video (not audio-only, because `get_frames` needs the video file). **Short-circuits when `source.mp4` already exists on disk and the URL slot is empty or `upload:`-prefixed** — just ffprobes the existing file. This is how upload-mode sessions skip yt-dlp entirely.
   - `youtube.trim_video` — *only when `clip_start_sec` / `clip_end_sec` are set on the session.* Re-encodes `source.mp4` in place to the requested window; downstream tools reference timestamps relative to the trimmed file.
   - `youtube.extract_audio` — ffmpeg extracts `.m4a` from the video
   - `transcribe.transcribe` — HF Whisper via raw HTTP (not OpenAI-compatible), returns word-level timestamps. Uses a cross-session `transcript_cache` keyed on `(youtube_url, clip_start, clip_end)`; **bypassed for upload sessions** (filename isn't a stable content key), but per-session resume still works via `step_results`.

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
| `generate_reaction_image` | Runway `gen4_image` | `{"asset_id": str}` |
| `generate_animated_reaction` | Runway `gen4.5` | `{"asset_id": str, "duration_sec": int}` |
| `generate_sound_effect` | Runway `eleven_text_to_sound_v2` | `{"asset_id": str, "duration_sec": int}` |
| `generate_character_video` | Runway `gwm1_avatars` (avatar_videos) | `{"asset_id": str, "duration_sec": float}` |
| `isolate_voice` | ffmpeg slice + Runway `eleven_voice_isolation` | `{"asset_id": str, "duration_sec": float}` |
| `finalize_reel` | pydantic validation + writes plan.json | signals loop exit |

Generated assets are saved under `media/sessions/<session_id>/tools/` with filenames `<type>_<asset_id>.<ext>`. The `SessionCtx.assets` dict maps `asset_id → {kind, path, duration_sec, tool}`.

### Checkpointing / resumption (`app/pipeline/checkpoints.py`)

Every expensive operation goes through `checkpointed(session_id, step_key, fn, ...)`. On the first run it executes and writes to `step_results` table. On retry/resume it returns the cached result without re-calling Runway or HF. Step keys: `"download_video"`, `"trim_video"` (only when clip bounds set), `"extract_audio"`, `"transcribe"`, `"assemble"` for pre-agent steps; `"tool:<turn>:<call_id>"` for tool calls.

`POST /sessions/{id}/resume` re-runs the runner; `_seed_assets_from_step_results` replays completed tool results back into `ctx.assets` so plan validation still works.

### Events / SSE (`app/pipeline/events.py`, `app/routes/sessions.py`)

`publish(session_id, type, payload)` (in `events.py`) writes to the `events` table and fans out to in-process `asyncio.Queue` subscribers. The SSE handler `GET /sessions/{id}/events` (in `routes/sessions.py`) backfills missed events from DB using `Last-Event-ID`, then awaits queue messages with a 15s `asyncio.wait_for` timeout — on timeout it emits a `heartbeat` event so proxies don't drop the connection.

### Database (`app/db.py`)

SQLite, stdlib `sqlite3`, no ORM. Four tables: `sessions`, `events` (append-only, drives SSE and UI history), `step_results` (per-session resumption cache), `transcript_cache` (cross-session Whisper cache keyed on `(youtube_url, clip_start_sec, clip_end_sec)` — `_CLIP_UNSET = -1.0` is the sentinel for unset clip bounds since SQLite treats NULL as distinct in PKs).

### LLM clients (`app/llm/`)

- `kimi_client.py` — plain `openai.OpenAI` pointed at `OPENAI_API_BASE_URL` (HF router), cached with `lru_cache`. **No retry wrapper here** — retries live around `_chat()` in `app/agent/loop.py:19` (tenacity, 4 attempts, exponential jitter on `RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`).
- `vision_client.py` — same endpoint and model, separate client used only inside `get_frames`. Sends base64 image data URIs in a one-shot user message. Has its own `tenacity` retry.

### Config (`app/config.py`)

`pydantic-settings` `Settings` singleton. `.env` values **override** shell env (explicit `_load_dotenv_override` before pydantic loads). Copy `.env.sample` to `.env` and fill in keys before running.

Key env vars:
- `RUNWAY_API_KEY` — Runway API key
- `OPENAI_API_KEY` / `HF_TOKEN` — HF token (same value; `HF_TOKEN` falls back to `OPENAI_API_KEY` if unset)
- `OPENAI_API_BASE_URL` — default `https://router.huggingface.co/v1`
- `OPENAI_MODEL_NAME` — default `moonshotai/Kimi-K2.6:fireworks-ai`
- `CHARACTER_AVATAR_PRESET` — Runway preset id (default `influencer`)
- `MIN_REEL_DURATION_SEC` — minimum allowed reel length (default `10.0`)
- `MAX_REEL_DURATION_SEC` — maximum allowed reel length (default `60.0`)
- `MAX_VIDEO_DURATION_SEC` — max source-video length in seconds (default `600`). Enforced for both URL downloads and uploads.
- `MAX_AGENT_TURNS` — hard cap on orchestrator loop iterations (default `25`).

### Optional runtime files

- `cookies_yt.txt` at repo root — Netscape-format YouTube cookies. If present, `app/pipeline/youtube.py` builds `YT_DLP` with `--cookies <path>`. Useful when running on a residential IP that needs auth; rarely effective on cloud/datacenter IPs.

The reel's total duration is **derived** from the plan, not declared by the model: it equals
the final track's `reel_end`. `finalize_reel` rejects plans whose derived total falls outside
`[MIN_REEL_DURATION_SEC, MAX_REEL_DURATION_SEC]`, and writes the derived value into `plan.json`
under `duration_sec` for `assemble.py` to consume.

### Frontend

Server-rendered Jinja2 HTML (`app/templates/`). No JS framework. The index page (`index.html`) form posts as `multipart/form-data` with an optional URL field and an optional `video_file` upload (one is required); it also includes a collapsed `<details>` disclaimer pointing cloud/EC2 users at upload mode with both a web-downloader link and the exact `yt-dlp` CLI command. The session detail page (`session.html`) uses the browser's native `EventSource` API to consume the SSE stream and renders each event type differently (step checklist, collapsible thinking blocks, tool call/result rows, final video player). Upload sessions display the URL slot as `📁 <filename>` instead of a link.

### Tracing

No tracing stack is running by default. Langfuse config keys (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) are accepted by `config.py` but not wired up. The SSE event stream (`GET /sessions/{id}/events`) provides live visibility into every agent step and tool call.

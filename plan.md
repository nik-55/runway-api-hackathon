# ReelAgent — Implementation Plan

This is the implementation plan for the system described in `final_idea.md`. Read that first.
This plan is the "how"; the idea doc is the "what".

---

## 0. Mental Model — What We Are Building

**One sentence:** A FastAPI server that takes a YouTube URL + optional direction, runs a single
Kimi K2.6 thinking-model agent loop with Runway tools, and produces a 20-second reaction reel.

**Two non-obvious commitments from the idea doc that the implementation must honour:**

1. **The orchestrator is the sole decision-maker.** There is no fixed pipeline of
   "find moment → write commentary → generate assets → assemble". The model decides what to
   call, in what order, with what arguments. Our code just hosts the loop and executes tools.
2. **The orchestrator never sees images directly.** `get_frames` runs a vision model
   internally and returns **text only**. Raw frames never enter the orchestrator's context.
   This keeps its 128K context lean for the long reasoning trace.

Everything else in this plan exists to support those two facts.

---

## 1. Tech Stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13 | user spec |
| HTTP server | FastAPI + uvicorn | user spec |
| DB | SQLite (via `sqlite3` stdlib + thin wrapper) | user spec, single-user hackathon scope |
| LLM SDK | `openai` package, base_url → HF router | Kimi K2.6 is OpenAI-compatible on HF |
| Runway | `runwayml` Python SDK | user spec, do **not** hand-roll HTTP |
| STT | HF Inference (Whisper large-v3-turbo) via `requests` | not OpenAI-compatible, raw binary upload |
| Tracing | `langfuse` | user spec |
| Media | `yt-dlp`, `ffmpeg` (subprocess) | standard |
| Frontend | Server-rendered HTML via `Jinja2` + SSE | user spec — no SPA |
| Background work | FastAPI `BackgroundTasks` + `asyncio.create_task`, single worker | hackathon scale |
| Containerisation | Dockerfile + docker-compose with langfuse stack | user spec |

**Explicit non-choices:** no LangChain, no Celery, no Redis, no Postgres, no React.

---

## 2. Project Structure

```
runway-hackathon/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, route registration, startup
│   ├── config.py                # env loading (pydantic-settings)
│   ├── db.py                    # sqlite connection + schema bootstrap
│   ├── logging_setup.py         # stdout + logs/ rotating file handler, .debug enabled
│   ├── routes/
│   │   ├── pages.py             # GET /, GET /sessions/{id} — HTML
│   │   ├── sessions.py          # POST /sessions, GET /sessions/{id}/events (SSE), GET /sessions/{id}/output
│   │   └── static.py            # serve media/ as /media (only completed outputs)
│   ├── pipeline/
│   │   ├── runner.py            # entry point per session — drives pre-agent + agent + assembly
│   │   ├── checkpoints.py       # store/load step results, idempotent step decorator
│   │   ├── youtube.py           # yt-dlp wrapper — download_audio, download_video
│   │   ├── transcribe.py        # HF whisper call → word-timestamped transcript
│   │   ├── assemble.py          # ffmpeg assembly from the model's plan
│   │   └── events.py            # publish progress events to DB + SSE pub/sub
│   ├── agent/
│   │   ├── loop.py              # the orchestrator loop (chat-completions w/ tools)
│   │   ├── system_prompt.py     # the big system prompt (see §10)
│   │   ├── tools/
│   │   │   ├── __init__.py      # tool registry + JSON schemas for OpenAI tools API
│   │   │   ├── get_frames.py
│   │   │   ├── generate_reaction_image.py
│   │   │   ├── generate_animated_reaction.py
│   │   │   ├── generate_sound_effect.py
│   │   │   ├── generate_character_video.py
│   │   │   ├── isolate_voice.py
│   │   │   └── finalize_reel.py        # the "I'm done, here's the assembly plan" tool
│   │   └── runway_client.py     # singleton RunwayML() + retry wrapper
│   ├── llm/
│   │   ├── kimi_client.py       # OpenAI client pointed at HF router, with langfuse hook
│   │   └── vision_client.py     # vision model used inside get_frames (NOT exposed to orchestrator)
│   └── templates/
│       ├── base.html
│       ├── index.html           # session list + new-session form
│       └── session.html         # SSE-driven step viewer + final video player
├── media/                       # gitignored, docker volume — all generated artefacts
│   └── sessions/<session_id>/
│       ├── source.m4a           # downloaded audio
│       ├── source.mp4           # downloaded video (for ffmpeg frames + cuts)
│       ├── transcript.json      # whisper output w/ word timestamps
│       ├── tools/
│       │   ├── reaction_image_<call_id>.png
│       │   ├── animated_<call_id>.mp4
│       │   ├── sfx_<call_id>.mp3
│       │   ├── character_<call_id>.mp4
│       │   └── isolated_<call_id>.mp3
│       ├── plan.json            # orchestrator's final assembly plan
│       └── reel.mp4             # final output
├── logs/                        # gitignored, rotating files
├── data/
│   └── reelagent.sqlite         # gitignored, docker volume
├── Dockerfile
├── docker-compose.yml           # app + langfuse + langfuse-db
├── requirements.txt
├── .env.sample
├── .env                         # gitignored
├── .dockerignore
├── .gitignore
├── final_idea.md
└── plan.md                      # this file
```

---

## 3. Database Schema (SQLite)

Three tables. Append-only event log + tool result cache for resumption.

```sql
CREATE TABLE sessions (
    id            TEXT PRIMARY KEY,           -- uuid4 hex
    youtube_url   TEXT NOT NULL,
    direction     TEXT,                       -- nullable user direction
    status        TEXT NOT NULL,              -- queued|running|failed|completed
    created_at    INTEGER NOT NULL,           -- unix sec
    updated_at    INTEGER NOT NULL,
    output_path   TEXT,                       -- relative path under media/
    failure       TEXT                        -- last error message if failed
);

CREATE TABLE events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    seq           INTEGER NOT NULL,           -- monotonic per session
    type          TEXT NOT NULL,              -- step.started|step.completed|step.failed|
                                              -- agent.thinking|agent.tool_call|agent.tool_result|
                                              -- agent.message|agent.final|log
    payload       TEXT NOT NULL,              -- JSON
    created_at    INTEGER NOT NULL,
    UNIQUE(session_id, seq)
);
CREATE INDEX events_by_session ON events(session_id, seq);

-- The resumption layer. Keyed by deterministic (session, step_key).
-- step_key for tool calls = stable hash of (tool_name, normalised args).
-- step_key for pre-agent steps = literal string e.g. "download_audio".
CREATE TABLE step_results (
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    step_key      TEXT NOT NULL,
    status        TEXT NOT NULL,              -- completed|failed
    result        TEXT NOT NULL,              -- JSON (small) — large outputs go to media/
    created_at    INTEGER NOT NULL,
    PRIMARY KEY(session_id, step_key)
);
```

**Why this schema:**
- `events` is the source of truth for "what is this session doing right now" — drives the SSE
  stream and the persisted UI history (the user explicitly asked for verbose history per session).
- `step_results` is the resumption cache. Any expensive operation (Runway calls, whisper,
  yt-dlp) writes here on success. On retry, we replay results from this table without re-billing.

---

## 4. Pipeline — Pre-Agent Deterministic Stage

Before the agent loop starts, we do a fixed sequence. Each step is wrapped by the
`@checkpointed("<step_key>")` decorator that consults `step_results` first.

| Step | Function | Output | Notes |
|---|---|---|---|
| 1 | `download_video` | `media/.../source.mp4` | yt-dlp; reject if duration > 10 min |
| 2 | `extract_audio` | `media/.../source.m4a` | ffmpeg from source.mp4 (single download, two files) |
| 3 | `transcribe` | `media/.../transcript.json` | HF Whisper, word-level timestamps |
| 4 | `start_agent` | (kicks off agent loop) | passes transcript + direction |

> **Deviation from idea doc:** the doc says "yt-dlp: download audio stream only". That
> conflicts with `get_frames` needing the video file. We download video and extract audio,
> which is one network round trip and gives us both. Cheap.

**Each pre-agent step emits two events:** `step.started` and `step.completed|step.failed`,
both with the step name in payload. UI renders these as a checklist before the agent log.

---

## 5. The Orchestrator Agent Loop

This is the core. It's a hand-written loop — no framework.

```
build initial messages = [system_prompt, user_message(transcript+direction)]
loop forever:
    response = kimi.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
    )
    msg = response.choices[0].message

    # persist + stream — never drop reasoning_content
    emit("agent.thinking", msg.reasoning_content) if present
    emit("agent.message",  msg.content)           if present

    messages.append(msg)   # we keep the full assistant message including tool_calls

    if not msg.tool_calls:
        # model produced free text without calling finalize_reel — nudge it back
        messages.append({"role":"user","content":
            "You must either call a tool or call finalize_reel(plan) to end. Continue."})
        continue

    # execute all tool_calls in parallel (asyncio.gather), capture per-call results
    results = await asyncio.gather(*[run_tool(c) for c in msg.tool_calls],
                                   return_exceptions=True)

    for call, result in zip(msg.tool_calls, results):
        emit("agent.tool_call", call)
        if isinstance(result, Exception):
            payload = {"error": str(result), "type": type(result).__name__}
            emit("agent.tool_result", {"call_id": call.id, **payload})
            messages.append({"role":"tool","tool_call_id":call.id,
                             "content": json.dumps(payload)})
        else:
            emit("agent.tool_result", {"call_id": call.id, "result": result})
            messages.append({"role":"tool","tool_call_id":call.id,
                             "content": json.dumps(result)})

    # finalize_reel sets a flag
    if any(c.function.name == "finalize_reel"
           and not isinstance(r, Exception)
           for c, r in zip(msg.tool_calls, results)):
        break

# post-loop: hand the persisted plan.json to the assembly stage
```

**Key properties:**
- Loop never prunes `messages`. Per user spec — Kimi has 128K context, the trace fits.
- Errors are converted to `tool` role messages so the model can reason about and recover from
  them. We do not raise out of the loop on a single tool failure.
- `finalize_reel` is itself a tool. The model "ends" by calling it with the assembly plan as
  argument. We validate the plan inside the tool — if invalid, the tool returns an error and
  the loop continues.
- A hard cap (`MAX_AGENT_TURNS`, default 25) prevents runaway loops; on hit, mark session
  failed with a clear message.
- Every chat completion is wrapped in `@retry(stop=stop_after_attempt(4),
  wait=wait_exponential_jitter())` for transient HF errors.

**Resumption note:** if the process dies mid-loop, we restart by replaying the events table
to rebuild `messages`, then re-issue the next chat completion. Tool results that completed
are already in the events log, so we don't re-invoke Runway. Tools that were *in flight*
when we died will be re-invoked, which is acceptable — they're idempotent at the model layer
(slightly different output, but the model will adapt).

A stronger version: store every assistant message and every tool result as a `step_result`
keyed by `(turn_idx, call_id)`. On resume, we replay them verbatim. This is the version we
implement — straightforward and matches user's "next retry start from where it failed" ask.

---

## 6. Tools

Each tool is a Python coroutine `async def call(session_ctx, **kwargs) -> dict`. Each has a
JSON schema in `tools/__init__.py:TOOL_SCHEMAS` exposed to the model in OpenAI tool-calling
format. Result dicts are designed to be small and copy-pasteable into the model's context.

### 6.1 `get_frames(start_sec, end_sec, prompt) -> {"answer": str}`

- ffmpeg samples N frames evenly across `[start_sec, end_sec]` (cap N at e.g. 6).
- Frames are passed with `prompt` to a vision model in a **separate** chat completion.
  Kimi K2.6 is natively multimodal — we use the same model for this sub-call by sending
  `image_url` content blocks (base64 data URIs) in a one-shot user message. No second
  provider, no extra key.
- The architectural point from the idea doc still stands: this is a separate API call. The
  raw image blobs never enter the orchestrator's `messages` list. Only the text answer is
  appended as a tool result. This keeps the main trace context small even after many calls.
- Returns **only** `{"answer": "<vision model text>"}`. Raw images never returned.
- Implemented in `app/llm/vision_client.py` so the path is clearly distinct from the
  orchestrator client even though both point at Kimi.

### 6.2 `generate_reaction_image(prompt, ratio="720:1280") -> {"asset_id": str, "duration_sec": null}`

- `client.text_to_image.create(model="gen4_image_turbo", prompt_text=prompt,
  ratio=ratio).wait_for_task_output()`
- Download `task.output[0]` to `media/.../tools/reaction_image_<asset_id>.png`.
- Return a stable `asset_id` (uuid). The model references this in its plan.
- Default to `gen4_image_turbo` (2 credits) — cheap, quality is fine for meme beats.

### 6.3 `generate_animated_reaction(prompt, duration) -> {"asset_id": str, "duration_sec": int}`

- `client.text_to_video.create(model="gen4_turbo" if image else "gen4.5", ...)`. Actually
  `gen4_turbo` requires an image. For text-only short clips use `gen4.5` (2-10s, 12 c/s) or
  `veo3.1_fast` (10-15 c/s). Default to `gen4.5` at 5s. Clamp `duration` to [2, 4].
- Ratio: `720:1280` (vertical reel).
- Download to `media/.../tools/animated_<asset_id>.mp4`.

### 6.4 `generate_sound_effect(prompt, duration) -> {"asset_id": str, "duration_sec": int}`

- `client.sound_effect.create(model="eleven_text_to_sound_v2",
  prompt_text=prompt).wait_for_task_output()`. The Runway endpoint accepts an optional
  duration — we pass it through.
- Download to `media/.../tools/sfx_<asset_id>.mp3`.

### 6.5 `generate_character_video(script, voice_preset="ruby") -> {"asset_id": str, "duration_sec": float}`

- Uses `POST /v1/avatar_videos` (per `notes/runway_generate_video.md`). The Python SDK
  exposes this — we'll verify the exact attribute path (`client.avatar_videos.create(...)`)
  via `+rw-fetch-api-reference` during impl. If it's not surfaced, fall back to
  `client.post(...)` with the typed body.
- Body shape:
  ```python
  client.avatar_videos.create(
      model="gwm1_avatars",
      avatar={"type": "runway-preset", "presetId": <CHARACTER_PRESET>},
      speech={
          "type": "text",
          "text": script,                                     # contains [emotion] markers
          "voice": {"type": "preset", "presetId": voice_preset},
      },
  ).wait_for_task_output()
  ```
- The `script` includes inline emotion markers — see Open Question Q3 about whether the
  preset TTS interprets them.
- Probe the duration of the resulting mp4 with `ffprobe` and return it.

### 6.6 `isolate_voice(start_sec, end_sec) -> {"asset_id": str, "duration_sec": float}`

- We slice `source.m4a` to the requested window with ffmpeg (saves credits — voice isolation
  is 1 credit/6 sec).
- Upload the slice via `client.uploads.create_ephemeral(open(..., "rb"))` to get a
  `runway://` URI.
- `client.voice_isolation.create(model="eleven_voice_isolation",
  audio_uri=upload.runway_uri).wait_for_task_output()`.
- Download to `media/.../tools/isolated_<asset_id>.mp3`.

> Note: tool takes `start/end` seconds (referencing the source video timeline), not a
> `clip_url`. The doc says `isolate_voice(clip_url)` but the orchestrator doesn't have
> upload-able clip URLs — it has timestamps. This is a minor reshape that makes the tool
> usable.

### 6.7 `finalize_reel(plan) -> {"ok": true} | {"error": ..., "issues": [...]}`

- The plan schema (validated with pydantic):
  ```json
  {
    "duration_sec": 20,                              // must equal 20
    "ratio": "720:1280",
    "moment": {"start_sec": 124.3, "end_sec": 137.8, "why": "..."},
    "commentary_script": "[disbelief] He actually...",   // for record only — already submitted via tool
    "tracks": [
      {
        "kind": "video",
        "source": {"type": "original", "start_sec": 124.3, "end_sec": 133.0},
        "reel_start": 0.0, "reel_end": 8.7,
        "audio": "isolated:<asset_id>"   // or "original" or "off"
      },
      {
        "kind": "video",
        "source": {"type": "asset", "asset_id": "<reaction_image_or_animated>"},
        "reel_start": 8.7, "reel_end": 11.0,
        "audio": "off"
      },
      {
        "kind": "video",
        "source": {"type": "asset", "asset_id": "<character_video_asset_id>"},
        "reel_start": 11.0, "reel_end": 20.0,
        "audio": "asset"
      }
    ],
    "overlays": [
      {
        "asset_id": "<character_video_asset_id>",
        "reel_start": 0.0, "reel_end": 11.0,
        "position": "bottom-right", "scale": 0.28
      }
    ],
    "audio_overlays": [
      {"asset_id": "<sfx_asset_id>", "reel_start": 8.7, "reel_end": 9.5, "gain_db": -3}
    ]
  }
  ```
- Validation rules: tracks tile [0, duration_sec) with no gap or overlap; every referenced
  `asset_id` exists; `moment.end - moment.start <= 20`; total duration is exactly 20s.
- On invalid → return `{"error": ..., "issues": [...]}` so the model can correct itself in
  the next turn.
- On valid → persist to `plan.json` and signal loop exit.

---

## 7. Final Assembly (post-agent)

Pure ffmpeg pipeline driven by `plan.json`. No Runway calls here.

Strategy — build with a single ffmpeg invocation using `-filter_complex`:
1. For each `tracks[i]`: `[trim/atrim]` from the source asset, then `[scale]` to 720x1280 (with
   `force_original_aspect_ratio=decrease`+`pad` for non-vertical sources).
2. `concat` the trimmed video tracks in `reel_start` order to form the base video stream.
3. For each `overlays[i]`: `[overlay]` the asset on top, with `enable='between(t,start,end)'`.
4. Build audio similarly: `concat` per-track audio (respecting `audio: original|off|isolated|asset`),
   then `amix` any `audio_overlays`.
5. Output: `media/.../reel.mp4` at 720x1280, 30fps, h264, ~6Mbps.

Probe each asset with ffprobe at start; if a generated clip is shorter than its planned slot,
freeze the last frame (`tpad`) — saves us from re-prompting the model.

On success: update `sessions.status='completed'`, `output_path='media/.../reel.mp4'`, emit
`step.completed` for `assemble`. The HTML page polls/SSE-listens and reveals the player.

---

## 8. Frontend (HTML over FastAPI + SSE)

Three pages, all server-rendered Jinja:

### `GET /` — index

- List of sessions (id, url, status, created, link to detail).
- Form: `youtube_url`, `direction` (optional), submit → `POST /sessions`.

### `POST /sessions`

- Validates URL, inserts `sessions` row with `status=queued`, kicks off
  `asyncio.create_task(runner.run(session_id))`, redirects to `/sessions/{id}`.

### `GET /sessions/{id}` — detail

- Renders existing events from DB (so refresh shows full history).
- Subscribes to `EventSource('/sessions/{id}/events')` for live updates.
- Renders each event by type:
  - `step.*` → checklist row with spinner/check/x.
  - `agent.thinking` → collapsed `<details>` ("Model thinking — N tokens"). Expand to show
    full reasoning_content. Verbose by design (user spec).
  - `agent.tool_call` → "→ called `<tool>(args)`".
  - `agent.tool_result` → indented result preview (asset_id + thumbnail if image).
  - `agent.message` → blockquote of free-text reply.
  - `agent.final` → green "Plan finalized" with collapsible plan JSON.
- When `sessions.status=completed`, embed `<video controls src="/media/sessions/{id}/reel.mp4">`
  + download button.

### `GET /sessions/{id}/events` — SSE

- Streams events with `seq > last_seq` (Last-Event-ID supported).
- In-process pub/sub: a `dict[session_id, list[asyncio.Queue]]` plus a coroutine that fans
  out new events from `events.publish(...)` to all subscribers. No Redis.
- Sends a `heartbeat` comment every 15s to defeat proxy timeouts.

---

## 9. Resumption / Idempotency

User spec: "Runway api calls are expensive so if possible make sure next retry start from
where it failed in pipeline."

**Mechanism:** every expensive operation goes through `pipeline/checkpoints.py`:

```python
async def checkpointed(session_id, step_key, fn, *args, **kwargs):
    cached = db.get_step_result(session_id, step_key)
    if cached and cached.status == "completed":
        return json.loads(cached.result)
    try:
        result = await fn(*args, **kwargs)
    except Exception as e:
        db.put_step_result(session_id, step_key, "failed", {"error": str(e)})
        raise
    db.put_step_result(session_id, step_key, "completed", result)
    return result
```

**Step keys:**
- Pre-agent: literal `"download_video"`, `"extract_audio"`, `"transcribe"`.
- Tool calls: `"tool:<turn_idx>:<call_id>"` — the model's own `tool_call.id` is a stable
  per-turn identifier; combined with the turn index it's globally unique within a session.
- Agent turn: `"turn:<turn_idx>"` stores the assistant message itself so we can replay
  message history without re-calling the LLM.

**Restart entry point:** `runner.run(session_id, resume=True)` rebuilds `messages` by
replaying `step_results` for `turn:*` and `tool:*`, then re-enters the loop at the next
turn. Pre-agent steps are auto-skipped because their step_results are present.

We add a `POST /sessions/{id}/resume` route bound to a button on failed sessions.

---

## 10. The System Prompt (the most important file)

The orchestrator is a **thinking model** (Kimi K2.6 with `reasoning_content`). The prompt
should *not* re-implement the chain of thought — the model does that itself — but should
**structure** what it reasons *about*. Pattern below.

Key sections (full text written in `agent/system_prompt.py`):

1. **Identity & job** — "You are ReelAgent. You have one job: turn this transcript into a
   20-second vertical reaction reel by autonomously orchestrating tools. There is no
   pre-defined pipeline. You decide what to do."
2. **Hard rules** —
   - Final reel is exactly 20.0 seconds.
   - You MUST call `generate_character_video` with the commentary script.
   - You MUST call `isolate_voice` for any window of original audio you keep on.
   - You end the session by calling `finalize_reel(plan)`. Nothing else ends it.
3. **The three decisions, in order of priority** — verbatim re-statement of "Decision 1/2/3"
   from the idea doc, because these are non-negotiable.
4. **Reasoning structure for each turn** — explicit CoT scaffold (the model still produces
   `reasoning_content`; this just guides what it considers):
   > Before every tool call, reason through:
   > (a) What do I still not know? (b) What am I about to spend credits on? (c) What is the
   > expected output and how will I use it? (d) Am I duplicating an earlier call?
   >
   > Before `finalize_reel`, reason through:
   > (a) Does the plan tile [0, 20] exactly? (b) Is every asset_id present in tool results?
   > (c) Does the cut sequence make narrative sense? (d) Is the character on screen at the
   > right moments?
5. **Tool usage hints** —
   - `get_frames` is cheap (local) — use it freely when transcript is ambiguous.
   - Runway tools are expensive — never call them speculatively. Have a concrete plan first.
   - Issue independent Runway calls in the **same assistant turn** so they execute in
     parallel (we await with `asyncio.gather`).
6. **Emotion marker vocabulary** — the exact set: `[shocked]`, `[laughing]`, `[disbelief]`,
   `[serious]`, `[sarcastic]`, `[excited]`, `[deadpan]`, `[pause]`. Plus a one-line
   description of each.
7. **Failure handling** — "If a tool returns `{error: ...}`, read it carefully. Many errors
   are recoverable by changing your prompt or arguments. Do not give up — adapt."
8. **Output schema for finalize_reel** — embedded JSON example so the model knows the exact
   shape (also enforced by pydantic).

**Tone:** terse, declarative, no hedging. The model has 128K context — we can afford ~3-4K
tokens of system prompt and it's worth it. The first user message is just
`{transcript_json, user_direction}`.

---

## 11. Logging & Tracing

- **stdlib logging** configured in `logging_setup.py`:
  - Root level `INFO`, our app loggers `DEBUG`.
  - Two handlers: `StreamHandler(stdout)` and `RotatingFileHandler(logs/app.log, 10MB x 5)`.
  - Format includes session_id when present (via contextvars).
- **`.debug` calls everywhere expensive happens** — every tool entry/exit, every Runway
  request body, every HF response with truncation, every ffmpeg command line. User spec.
- **Langfuse:**
  - `langfuse-python` SDK; one trace per session (`session_id` as trace id).
  - Wrap each Kimi `chat.completions.create` with `@observe()` (or `langfuse.openai` drop-in
    if compatible with HF base_url — verify; fallback to manual).
  - Each tool call becomes a span under the trace.
  - In docker-compose, run langfuse locally (web + worker + postgres + clickhouse minimal
    stack — official `langfuse/langfuse:3` compose snippet).
  - `LANGFUSE_HOST=http://langfuse-web:3000`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
    in `.env.sample`.

---

## 12. Retries

Use `tenacity`:
- HF chat completion: 4 attempts, exponential jitter, retry on `RateLimitError`,
  `APIConnectionError`, `APITimeoutError`, 5xx.
- HF Whisper: 3 attempts, exponential jitter, retry on connection / 5xx.
- Runway SDK: the SDK has built-in retries for transient errors; we add an outer
  3-attempt retry only for `APIConnectionError` and 5xx. Do **not** retry `SAFETY.INPUT.*`
  or `400` — surface to the model so it can rewrite the prompt.
- `wait_for_task_output` default 10-min timeout is fine for our durations.
- yt-dlp: 2 attempts.

---

## 13. Docker Setup

### Dockerfile
- `python:3.13-slim` base
- Install `ffmpeg` via `apt-get`
- `pip install -r requirements.txt`
- Copy `app/`, `final_idea.md`, `plan.md`
- `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`

### docker-compose.yml
- `app` service: build from Dockerfile, mount `./media:/app/media`, `./logs:/app/logs`,
  `./data:/app/data`, env_file `.env`, depends_on `langfuse-web`.
- `langfuse-web` + `langfuse-worker` + `langfuse-db` (postgres) + `langfuse-clickhouse`:
  pulled verbatim from official langfuse v3 self-host compose snippet, trimmed to minimum
  for local dev.

### .env.sample (additions)
```
RUNWAY_API_KEY=
OPENAI_API_KEY=                                  # HF token (hf_...)
OPENAI_API_BASE_URL=https://router.huggingface.co/v1
OPENAI_MODEL_NAME=moonshotai/Kimi-K2.6:fireworks-ai
STT_MODEL=openai/whisper-large-v3-turbo:fastest
HF_TOKEN=                                        # same as OPENAI_API_KEY for whisper

# vision sub-call inside get_frames — same Kimi endpoint, separate completion
VISION_MODEL_NAME=moonshotai/Kimi-K2.6:fireworks-ai

# character
CHARACTER_AVATAR_PRESET=influencer               # one of runway-preset values
CHARACTER_VOICE_PRESET=ruby

# langfuse
LANGFUSE_HOST=http://langfuse-web:3000
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# limits
MAX_AGENT_TURNS=25
MAX_VIDEO_DURATION_SEC=600
```

### .gitignore / .dockerignore (additions)
```
.env
.venv
media/
logs/
data/
__pycache__/
*.pyc
```

---

## 14. requirements.txt (initial)

```
fastapi>=0.115
uvicorn[standard]>=0.32
jinja2>=3.1
pydantic>=2.9
pydantic-settings>=2.6
python-multipart>=0.0.12

openai>=1.55                # HF router compatibility
runwayml>=3                 # verify exact version during impl
langfuse>=2.50

yt-dlp>=2024.12.0
requests>=2.32
httpx>=0.27
tenacity>=9.0
```

(SQLite is stdlib; `ffmpeg`/`ffprobe` are system binaries.)

---

## 15. Build Order (suggested)

This is the order in which to actually write the code so something runs end-to-end ASAP, then
each subsequent step adds capability.

1. **Skeleton + config + logging + DB** — `main.py`, `config.py`, `db.py`, `logging_setup.py`.
   Empty index page works.
2. **Pre-agent pipeline (offline)** — yt-dlp + ffmpeg + Whisper. CLI script that takes a URL
   and dumps `transcript.json`. Verify word timestamps (Open Q4).
3. **Runway client + one tool end-to-end** — wire `generate_reaction_image` against real
   Runway. Confirm SDK shape, `wait_for_task_output`, download flow.
4. **Agent loop with one tool** — Kimi via HF, single tool, no `finalize_reel` yet. Confirm
   `reasoning_content` is captured and tool calls round-trip.
5. **All remaining tools** — wire each, including the avatar_videos one (the riskiest;
   verify SDK exposure).
6. **`finalize_reel` + plan validation** — pydantic schema + agent loop exit.
7. **Assembly with ffmpeg** — produce a real 20s mp4 from a hand-written plan first,
   then from an agent-produced plan.
8. **HTML pages + SSE + event publishing** — wire the in-process pub/sub last, after the
   pipeline produces real events.
9. **Resumption** — implement `step_results` cache + resume route.
10. **Docker + langfuse compose** — run end-to-end in containers.
11. **Polish** — system prompt iteration on real outputs, error UX, README.

---

## 16. Open Questions (need user input)

These are the choices I cannot make alone — flagged so we can lock them before/during impl.

**LOCKED (user-confirmed):**
- Vision in `get_frames`: Kimi K2.6 is native multimodal — vision sub-call goes to the same
  HF endpoint. No second provider.
- Character avatar: Runway preset `influencer`.
- STT timestamps: try HF `return_timestamps=word` parameter first, fall back to
  `faster-whisper` locally if unsupported.
- Reel format: 9:16 vertical, 720x1280, 30fps.

**Still open:**

**Q1. Emotion markers — does the avatar TTS honour them?** The idea doc lists `[shocked]`,
`[laughing]`, etc. Runway `avatar_videos` with text input runs ElevenLabs TTS internally;
ElevenLabs supports a tag set (`[laughs]`, `[sighs]`, `[whispers]`, etc.) but exact
compatibility with our full list is unverified. Plan: ship the doc's vocabulary as-is and
verify on first end-to-end run; if a marker is ignored, map it to the closest supported tag
in the system prompt for next runs. Decide after seeing real output.

**Q2. Direction parsing.** When the user types "roast it" / "make it serious", paste verbatim
into the user message? Plan: yes, verbatim. Model handles tone.

---

## 17. Out of Scope (for hackathon)

- Auth / users / billing
- Batch processing
- Video > 10 minutes
- Multiple moments per reel
- User-editable plan (the agent decides; we ship what it produces)
- Custom avatar upload UI (single configured persona)

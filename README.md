# ReelAgent

**Paste a YouTube URL. Get a short reaction reel with a lip-synced AI commentator. No editing. No prompting. One input, one output.**

A single AI agent reads the transcript, picks the most interesting moment, writes commentary with an emotional delivery, calls Runway APIs for every media asset, and assembles the final vertical video — all autonomously.

---

## Demo

> *YouTube URL + optional direction → short vertical MP4 with a lip-synced character, reaction imagery, sound effects, and cleaned source audio — assembled in one agent loop.*

---

## What makes it interesting

Most highlight tools clip video. ReelAgent produces a **finished piece**: a short vertical reel with:

- A **lip-synced avatar** delivering commentary (not a voiceover, a face speaking)
- **Emotion markers** baked into the script (`[shocked]`, `[laughing]`, `[deadpan]`) so the character reacts, not just reads
- **Generated reaction imagery or animated beats** timed to the cut
- **Sound effects** placed at precise moments
- **Voice-isolated source audio** so the original clip is clean

The entire creative brief — which moment, what to say, how to say it, what to generate, how to assemble it — is decided by the agent, not by a fixed pipeline.

---

## Setup & Running

### Prerequisites

- Python 3.13
- `ffmpeg` installed on your system (`brew install ffmpeg` / `apt install ffmpeg`)
- A Runway API key — [get one at app.runwayml.com](https://app.runwayml.com)
- A Hugging Face token — [get one at huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (used for the Kimi K2.6 LLM + Whisper transcription)

---

### Option A — Local (no Docker)

```bash
# 1. Clone
git clone <repo-url>
cd runway-hackathon

# 2. Create virtualenv and install
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.sample .env
# Edit .env and fill in at minimum:
#   RUNWAY_API_KEY=rw-...
#   OPENAI_API_KEY=hf_...    (your HF token)

# 4. Run
uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

> Langfuse tracing is optional locally — leave `LANGFUSE_*` keys blank and it will be skipped.

---

### Option B — Docker Compose (includes Langfuse tracing)

```bash
cp .env.sample .env
# Fill in RUNWAY_API_KEY and OPENAI_API_KEY

docker compose up --build
```

- **ReelAgent UI:** [http://localhost:8000](http://localhost:8000)
- **Langfuse tracing dashboard:** [http://localhost:3000](http://localhost:3000)

Create a Langfuse account at localhost:3000, copy the project keys into `.env` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`), and restart `docker compose up` to enable tracing.

The compose stack includes Langfuse's full self-hosted v3 infrastructure (web, worker, Postgres, ClickHouse, Redis, MinIO).

---

### Environment variables reference

```
RUNWAY_API_KEY=               # Required — Runway API key
OPENAI_API_KEY=               # Required — HF token (hf_...)
OPENAI_API_BASE_URL=          # HF router (default: https://router.huggingface.co/v1)
OPENAI_MODEL_NAME=            # Orchestrator model (default: moonshotai/Kimi-K2.6:fireworks-ai)
VISION_MODEL_NAME=            # Vision sub-call model (default: same Kimi endpoint)
HF_TOKEN=                     # Falls back to OPENAI_API_KEY if not set

CHARACTER_AVATAR_PRESET=      # Runway avatar preset (default: influencer)
CHARACTER_VOICE_PRESET=       # Runway voice preset (default: ruby)

LANGFUSE_HOST=                # http://langfuse-web:3000 in Docker; blank to disable
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

MAX_AGENT_TURNS=25            # Hard cap on agent loop iterations
MAX_VIDEO_DURATION_SEC=600    # Reject videos longer than this (10 min)
```

---

## Using the UI

### 1. Submit a video

On the home page (`/`), paste a YouTube URL (≤ 10 minutes) and optionally type a direction:

- `"roast it"` — sarcastic, punchy take
- `"explain why this matters"` — serious framing
- `"make it funny"` — lean into absurdity
- Leave blank — the agent decides the tone from the content

Click **Generate**. You're immediately redirected to the session detail page.

### 2. Watch the agent work (live)

The session page streams everything the agent does in real time via Server-Sent Events:

| Event | What it means |
|---|---|
| `→ download_video` | yt-dlp is downloading the video |
| `✓ transcribe` | Whisper finished; word-level timestamps ready |
| `thinking (N chars)` | Kimi K2.6's reasoning trace — click to expand and see the model's chain of thought |
| `→ generate_character_video(...)` | Agent called the avatar API with the script + emotion markers |
| `← generate_character_video` | Asset downloaded; click to see duration |
| `→ finalize_reel(...)` | Agent submitted its assembly plan |
| `★ plan finalized` | Plan validated; ffmpeg assembly begins |
| `★ output ready` | Video player appears inline |

All events are persisted — refreshing the page shows the full history.

### 3. Get the reel

When the status badge turns **completed**, a video player appears on the session page. Click **Download** to save the MP4.

### 4. Resume a failed session

If a session fails mid-way (network error, Runway timeout, etc.), click **Resume** on the session page. The pipeline picks up from the last successful checkpoint — no Runway credits are re-spent on assets that already completed.

---

## Architecture

### The core idea

ReelAgent is not a fixed pipeline. There is no hard-coded sequence of "find moment → write commentary → generate assets → assemble." The agent is the sole decision-maker. The code just hosts an async loop and executes whatever tools the model calls.

```
User: YouTube URL + optional direction
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                  Pre-Agent Stage (deterministic)          │
│                                                           │
│  yt-dlp → source.mp4 (≤720p, ≤10 min)                   │
│     │                                                     │
│  ffmpeg extract → source.m4a (audio only)                │
│     │                                                     │
│  HF Whisper (large-v3-turbo)                             │
│     → transcript.json (full text + word timestamps)      │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│               Orchestrator Loop (Kimi K2.6)               │
│                                                           │
│  Input: transcript + user direction                       │
│                                                           │
│  Decision 1 — Find the moment                            │
│    Reads transcript, picks 8–14s window.                 │
│    If ambiguous: calls get_frames → text answer only.    │
│                                                           │
│  Decision 2 — Write the commentary                       │
│    5–7s script with inline emotion markers.              │
│    [shocked] / [laughing] / [sarcastic] / [deadpan] …   │
│                                                           │
│  Decision 3 — Design the reel + call tools               │
│    Decides what to generate, calls tools in parallel.    │
│    Ends by calling finalize_reel(plan).                  │
└──────────────────────────────────────────────────────────┘
        │
        │  Tool calls (run in parallel per turn via asyncio.gather)
        │
        ├──► get_frames(start, end, prompt)
        │      ffmpeg extracts frames → vision sub-call (Kimi)
        │      returns TEXT only — raw images never reach orchestrator
        │
        ├──► generate_reaction_image(prompt)
        │      Runway gen4_image (text→image, 9:16)
        │      → reaction_image_<id>.png
        │
        ├──► generate_animated_reaction(prompt, duration)
        │      Runway gen4.5 (text→video, 4/6/8s, 9:16)
        │      → animated_<id>.mp4
        │
        ├──► generate_sound_effect(prompt, duration)
        │      Runway eleven_text_to_sound_v2
        │      → sfx_<id>.mp3
        │
        ├──► generate_character_video(script)
        │      Runway gwm1_avatars (avatar_videos)
        │      ElevenLabs TTS with emotion markers, lip-synced video
        │      → character_<id>.mp4
        │
        ├──► isolate_voice(start_sec, end_sec)
        │      ffmpeg slices source audio → Runway eleven_voice_isolation
        │      → isolated_<id>.mp3
        │
        └──► finalize_reel(plan)
               Pydantic validates plan: tracks tile from 0 within configured range, all asset_ids exist
               Writes plan.json → signals loop exit
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                  Assembly (pure ffmpeg)                   │
│                                                           │
│  Reads plan.json. Single -filter_complex invocation:     │
│  - trim/scale/pad each track to 720x1280                 │
│  - concat tracks in timeline order                       │
│  - overlay character in corner with enable='between(t,…)'│
│  - mix isolated audio + SFX audio overlays               │
│  - output: reel.mp4 (h264, 720x1280, 30fps)             │
└──────────────────────────────────────────────────────────┘
        │
        ▼
  Final MP4, streamed to browser
```

---

### A typical reel structure the agent produces

```
Cold open    Original clip plays
              Character visible in bottom-right corner, silent

Build         Clip continues
              Original audio: ON (voice-isolated, background removed)
              Character in corner — reacting visually

Punch         Hard cut to generated reaction image
              Sound effect sting hits on the cut
              Original audio: OFF

Replay        Original clip resumes, key line replays
              Original audio: ON

Verdict       Character takes full frame — lip-synced monologue
              [shocked] He actually said this on camera.
              [pause]
              [laughing] And just moved on like it's nothing.
              [serious] But here's why this actually matters...
```

This is not fixed — the agent structures each reel differently based on the moment. A slow-burn controversial take gets different cuts than a sudden absurd blurt.

---

### Key design decisions

**The orchestrator never sees images directly.**
`get_frames` runs a separate vision completion internally and returns a plain-text answer. Raw frames never enter the orchestrator's `messages` list. This keeps the 128K context window lean across long agent traces with many tool calls.

**Tool calls within a turn run in parallel.**
When the agent issues multiple tool calls in a single assistant message (e.g. `generate_character_video` + `generate_sound_effect` + `isolate_voice`), they execute concurrently via `asyncio.gather`. This cuts Runway generation time significantly.

**`finalize_reel` is itself a tool, not an exit signal.**
The agent ends the session by calling `finalize_reel(plan)` with a structured JSON plan. Pydantic validates that: tracks tile from time 0 with no gaps or overlaps and total length within `[MIN_REEL_DURATION_SEC, MAX_REEL_DURATION_SEC]`, every `asset_id` referenced in the plan exists in the registry from prior tool results, and `generate_character_video` was called. If validation fails, the tool returns `{"error": ..., "issues": [...]}` and the loop continues — the model can correct itself.

**Full resumption without re-billing.**
Every expensive operation (Runway calls, Whisper, yt-dlp) is wrapped in a checkpoint that writes results to SQLite. On retry, the checkpoint returns the cached result. Pre-agent steps are skipped automatically. Agent turns are replayed from stored assistant messages. Failed sessions show a **Resume** button — continuing from the exact failure point.

**No fixed pipeline — the agent decides everything.**
The system prompt tells the model *what to consider* (the three decisions, pre-call reasoning, pre-plan checks) but does not tell it *what order to call tools*. Kimi K2.6's `reasoning_content` (chain-of-thought) is captured and streamed to the UI so you can see the model actually reasoning about the moment.

---

### Data flow per session

```
media/sessions/<session_id>/
├── source.mp4          ← yt-dlp download
├── source.m4a          ← ffmpeg audio extract
├── source.flac         ← converted for Whisper upload
├── transcript.json     ← word-level timestamps from Whisper
├── tools/
│   ├── reaction_image_<id>.png
│   ├── animated_<id>.mp4
│   ├── sfx_<id>.mp3
│   ├── character_<id>.mp4
│   └── isolated_<id>.mp3
├── plan.json           ← agent's final assembly plan (validated)
└── reel.mp4            ← final output
```

SQLite (`data/reelagent.sqlite`) holds three tables:
- `sessions` — status, URL, output path
- `events` — append-only log driving the SSE stream and UI history
- `step_results` — resumption cache keyed by step name or `tool:<turn>:<call_id>`

---

### Stack

| Layer | Technology |
|---|---|
| Web server | FastAPI + uvicorn |
| Orchestrator LLM | Kimi K2.6 (via HF router, OpenAI-compatible) |
| Speech-to-text | HF Whisper large-v3-turbo (binary upload, not OpenAI-compatible) |
| Video generation | Runway gen4.5 |
| Image generation | Runway gen4_image |
| Sound effects | Runway eleven_text_to_sound_v2 |
| Voice isolation | Runway eleven_voice_isolation |
| Lip-synced avatar | Runway gwm1_avatars (avatar_videos) |
| Media processing | ffmpeg / ffprobe (subprocess) |
| Database | SQLite (stdlib) |
| Frontend | Jinja2 HTML + browser EventSource (no JS framework) |
| LLM tracing | Langfuse (self-hosted via Docker Compose) |
| Retries | tenacity |

---

## Runway APIs used

| API | Use |
|---|---|
| `POST /v1/avatar_videos` (gwm1_avatars) | Lip-synced character video from script + emotion markers |
| `POST /v1/text_to_image` (gen4_image) | Reaction still image |
| `POST /v1/text_to_video` (gen4.5) | Animated reaction beat |
| `POST /v1/sound_effect` (eleven_text_to_sound_v2) | SFX sting |
| `POST /v1/voice_isolation` (eleven_voice_isolation) | Clean source audio |

---

## Constraints (hackathon scope)

- One reel per session (not batch)
- YouTube videos ≤ 10 minutes
- One moment per reel (the agent picks the best one)
- Reel length bounded by `MIN_REEL_DURATION_SEC` / `MAX_REEL_DURATION_SEC` (configurable via `.env`)
- Single configured character persona (set `CHARACTER_AVATAR_PRESET` in `.env`)

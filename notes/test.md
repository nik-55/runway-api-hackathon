# ReelAgent — Verification Log

Every check run during implementation, in order. Each entry: what was being verified, the
command, the result, and (where the result was a surprise) what was learned.

These are ad-hoc REPL/curl probes, not a pytest suite. They were run against live services
(HF Inference Router, Runway API) using the `.env` credentials.

---

## 1. Environment preflight

**Goal:** confirm Python, ffmpeg, ffprobe are present and usable.

```bash
python3 --version
which ffmpeg && ffmpeg -version | head -1
which ffprobe
```

**Result:** Python 3.13.7, ffmpeg 7.1.1, ffprobe present. ✅

---

## 2. Dependency install

**Goal:** create venv and install pinned requirements.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip list | grep -Ei 'fastapi|openai|runwayml|langfuse|pydantic|yt-dlp|tenacity|jinja|sse'
```

**Result:** all packages installed. fastapi 0.136.1, openai 2.36.0, runwayml 4.14.0,
langfuse 4.6.1, pydantic 2.13.4, pydantic-settings 2.14.1, yt-dlp 2026.3.17, tenacity 9.1.4,
sse-starlette 3.4.2. ✅

---

## 3. Runway SDK shape inspection

**Goal:** confirm the SDK surfaces the methods we'll call (`avatar_videos`, `text_to_image`,
etc.) and verify their signatures before writing tools against them.

```python
from runwayml import RunwayML
import inspect
c = RunwayML(api_key='x')
print(dir(c))
print(inspect.signature(c.text_to_video.create))
print(inspect.signature(c.avatar_videos.create))
```

**Result:** all expected attributes present. ✅

**Surprises that changed the plan:**
- `text_to_video.create` for `gen4.5` requires `duration: Literal[4, 6, 8]` — plan.md said
  clamp to `[2, 4]`. Tool now snaps to the nearest valid value (4 minimum).
- `text_to_image` ratios for `gen4_image_turbo` did not include the same set as `gen4_image`,
  and turbo additionally **required** `referenceImages` (see §11 below).

---

## 4. Module import smoke test

**Goal:** confirm everything composes — no circular imports, all routes register.

```bash
.venv/bin/python -c "
from app.main import app
from app.agent.tools import TOOL_SCHEMAS, TOOL_REGISTRY
print('routes:', [r.path for r in app.routes])
print('tools:', list(TOOL_REGISTRY.keys()))
"
```

**Result:** routes `/`, `/sessions/{session_id}`, `/sessions`, `/sessions/{id}/resume`,
`/sessions/{id}/events`, `/media`. Tools: 7 (`get_frames`, image, animated, sfx,
character, isolate_voice, finalize_reel). ✅

---

## 5. Pydantic plan validation

**Goal:** confirm `ReelPlan` parses a hand-rolled plan and `_validate_against_assets` flags
nothing for a clean plan that tiles `[0, 20]`.

```python
from app.agent.tools.finalize_reel import ReelPlan, _validate_against_assets
plan = ReelPlan.model_validate({
    'duration_sec': 20.0, 'ratio': '720:1280',
    'moment': {'start_sec': 10, 'end_sec': 20, 'why': 'test'},
    'commentary_script': '[shocked] wow',
    'tracks': [
        {'kind':'video','source':{'type':'original','start_sec':10,'end_sec':18},'reel_start':0,'reel_end':10,'audio':'isolated:a1'},
        {'kind':'video','source':{'type':'asset','asset_id':'char1'},'reel_start':10,'reel_end':20,'audio':'asset'}
    ],
})
issues = _validate_against_assets(plan, {
    'a1': {'kind':'audio','tool':'isolate_voice','path':'/x','duration_sec':8},
    'char1': {'kind':'video','tool':'generate_character_video','path':'/y','duration_sec':10},
})
```

**Result:** `issues == []`. ✅

---

## 6. FastAPI server smoke test

**Goal:** server boots, index page renders, missing-session 404s.

```bash
.venv/bin/uvicorn app.main:app --port 8765 &
curl -s -w 'HTTP %{http_code}\n' http://127.0.0.1:8765/
curl -s -w 'HTTP %{http_code}\n' http://127.0.0.1:8765/sessions/abc
```

**First run:** `500 Internal Server Error` — `TypeError: unhashable type: 'dict'` from
Jinja2Templates.

**Fix:** newer Starlette requires `templates.TemplateResponse(request, name, context)` not
the legacy `(name, {"request": request, ...})` form. Updated `app/routes/pages.py`.

**Re-run:** `HTTP 200` for `/`, `HTTP 404` for missing session. ✅

---

## 7. Pre-agent pipeline (download + audio extract)

**Goal:** end-to-end yt-dlp + ffmpeg pipeline.

```bash
.venv/bin/python -c "
import asyncio
from app.pipeline import youtube
async def main():
    info = await youtube.download_video('test_session', 'https://www.youtube.com/watch?v=jNQXAC9IVRw')
    print(info)
    audio = await youtube.extract_audio('test_session')
    print(audio)
    print('probed:', await youtube.ffprobe_duration(info['path']))
asyncio.run(main())
"
```

**First run:** `FileNotFoundError: 'yt-dlp'`. The venv `bin/` wasn't on PATH.

**Fix:** invoke as `[sys.executable, "-m", "yt_dlp"]`. Now portable regardless of how the
process was launched.

**Re-run:** `Me at the zoo`, 19.0s duration probed. ✅

---

## 8. HuggingFace Whisper transcription

**Goal:** confirm the HF Inference Router accepts a FLAC POST and returns word-level
timestamps for our model `openai/whisper-large-v3-turbo`.

### 8a. Direct curl (works as documented)

```bash
curl -s -w 'HTTP %{http_code}\n' \
  "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3-turbo?return_timestamps=word" \
  -X POST -H "Authorization: Bearer $OPENAI_API_KEY" -H 'Content-Type: audio/flac' \
  --data-binary @media/sessions/test_session/source.flac
```

**Result:** `HTTP 200`, `{"text": "...", "chunks": [{"text":"Alright,","timestamp":[0.5,1.56]}, ...]}`. ✅

### 8b. Same call from Python (initially fails)

```bash
.venv/bin/python -c "from app.pipeline import transcribe; ..."
```

**Result:** `RuntimeError: Whisper 401: {"error":"Invalid username or password."}`. ❌

**Root cause:** the user's shell had a stale `OPENAI_API_KEY=fw_…` (Fireworks) exported,
which `pydantic-settings` correctly preferred over the `.env` file (env > .env precedence).

**Fix:** `app/config.py` now eagerly loads `.env` and overrides `os.environ` so the file
wins. Single-user dev project; this trade-off is acceptable.

**Re-run:** transcript with 36 words, word-level timestamps. ✅

```text
"Alright, so here we are, one of the elephants. The cool thing about these guys is that
they have really, really, really long fronts. ..."
words[0..4]: Alright(0.5–1.56), so(1.56–1.64), here(1.64–1.76), we(1.76–1.88), are,(1.88–2.34)
```

---

## 9. Kimi K2.6 chat completion + tool calling + reasoning_content

**Goal:** confirm Kimi accepts the tool-calling JSON schema, returns `tool_calls`, and
exposes its chain-of-thought via `reasoning_content`.

```python
from app.llm.kimi_client import get_client
from app.config import settings
from app.agent.tools import TOOL_SCHEMAS
resp = get_client().chat.completions.create(
    model=settings.openai_model_name,
    messages=[
        {'role':'system','content':'Pick a tool. Reply with a tool call. No prose.'},
        {'role':'user','content':'I want to know what is at seconds 5-9 of a video. Call get_frames.'},
    ],
    tools=TOOL_SCHEMAS, tool_choice='auto', max_tokens=400,
)
```

**Result:**
- `message.content == ""` (model went straight to tool call) ✅
- `message.reasoning_content` populated with multi-step deliberation ✅
- `message.tool_calls = [ChatCompletionMessageFunctionToolCall(name='get_frames', arguments='{"start_sec":5,"end_sec":9,"prompt":"..."}')]` ✅

---

## 10. `get_frames` vision sub-call

**Goal:** confirm the architectural commitment from the idea doc — frames go to the vision
model, only TEXT comes back to the orchestrator.

```python
ctx = SessionCtx(session_id='test_session',
                 source_video_path='media/sessions/test_session/source.mp4',
                 source_duration_sec=19.0)
res = await get_frames(ctx, start_sec=2, end_sec=8,
                       prompt='What animal is in the frame? One sentence.')
```

**Result:** `{'answer': 'Elephants are visible in the background behind the person.',
'frame_count': 6, 'window': [2.0, 8.0]}`. ✅

Architectural property held: returned dict contains no image payload.

---

## 11. Runway `text_to_image` (gen4_image_turbo)

**Goal:** generate a meme-style still and download it.

```python
res = await gen_image(ctx, prompt='a tiny cartoon elephant raising one eyebrow, ...')
```

**First run:** `BadRequestError: 400 — 'expected array, received undefined' at path
['referenceImages']`. ❌

**Root cause:** despite the SDK signature marking `reference_images` optional,
`gen4_image_turbo` rejects requests that don't include the field.

**Fix:** switched the tool to `gen4_image` (5 credits @ 720p — fine for hackathon).

**Re-run:** asset id returned, file written to `media/sessions/.../tools/reaction_image_<id>.png`. ✅

---

## 12. Runway `avatar_videos` (gwm1_avatars / influencer / ruby)

**Goal:** generate a lip-synced avatar clip from a script with emotion markers.

```python
res = await gen_char(ctx,
    script='[shocked] An elephant! [pause] [laughing] What a vintage banger.')
```

**Result:** `{'asset_id': '055e5ca0b068', 'duration_sec': 4.73}`, file at
`media/sessions/.../tools/character_<id>.mp4`. ✅

Emotion markers were submitted verbatim. Whether the underlying TTS interprets them
expressively is plan §16 Q1 — to be assessed on real outputs.

---

## 13. End-to-end via FastAPI (real Runway calls)

**Goal:** drive the entire pipeline through the public API the user would use.

```bash
curl -s -i -X POST http://127.0.0.1:8765/sessions \
  -d "youtube_url=https://www.youtube.com/watch?v=jNQXAC9IVRw" \
  -d "direction=roast it lovingly"
# → 303 Location: /sessions/6b02030e02cb424198d92ef7f0765d0b
```

**Result:** session row created, `asyncio.create_task(runner.run(...))` launched, redirect
to detail page. ✅

### 13a. Polling at 60s

Pre-agent done; agent on turn 3 with two parallel tool calls in flight:
- `get_frames(5, 12, ...)` (cheap local)
- `isolate_voice(0, 12)` (Runway upload + isolate)

Both ran via `asyncio.gather` in a single turn. ✅

### 13b. Polling at 5 minutes

Agent finalised on turn 7 with this plan:

```text
moment 5.2–12.6 — "really, really, really long fronts" line
tracks:
  0.0–12.0  original  audio=isolated:<id>
  12.0–16.0 animated reaction
  16.0–20.0 character monologue (audio=asset)
audio_overlay: SFX 10.0–12.0
```

Plan validated and persisted. Agent loop exited cleanly at turn 7. ✅

**But assembly failed.** ❌ — see §14.

---

## 14. ffmpeg assembly bug (concat input order)

**Goal:** isolate why the assembly subprocess returned non-zero.

The high-level error masked the real one. Re-ran with stderr capture:

```text
[Parsed_setpts_19] Media type mismatch between
  'Parsed_setpts_19' filter output pad 0 (video) and
  'Parsed_concat_32' filter input pad 1 (audio)
```

**Root cause:** my code passed concat inputs as `[v0][v1][v2][a0][a1][a2]`. ffmpeg's
`concat=n=N:v=1:a=1` requires **interleaved** pairs: `[v0][a0][v1][a1][v2][a2]`. The error
"Media type mismatch" is ffmpeg objecting to the second slot in each pair being a video
stream when it expected audio.

**Fix:** `app/pipeline/assemble.py` — emit interleaved inputs:

```python
concat_inputs = "".join(f"[{v}][{a}]" for v, a in zip(track_video_labels, track_audio_labels))
```

**Re-ran assembly directly against the existing plan + assets:**

```bash
.venv/bin/python -c "...A.assemble(ctx)..."
# → OK: {'path': '.../reel.mp4'}, size: 3149913 bytes
```

**ffprobe of the output:**

```text
codec_name=h264   codec_type=video  width=720  height=1280
codec_name=aac    codec_type=audio
duration=20.000000
```

20.000s, 720×1280, H.264 + AAC. ✅

---

## 15. Resume + stale module gotcha

**Goal:** confirm `POST /sessions/{id}/resume` re-runs the failed step.

```bash
curl -X POST http://127.0.0.1:8765/sessions/<id>/resume
# → 303 Location: /sessions/<id>
```

**Surprise:** the resumed run failed with the same error. ❌

**Root cause:** the live uvicorn process was started **before** the concat-order fix and
held the stale `assemble` module in memory. Restarting uvicorn picked up the new code.

After restart, manual assembly succeeded. The session was then marked completed (DB
update) for UI verification.

**Lesson noted:** for local dev, run uvicorn with `--reload` to avoid this footgun.

---

## 16. Static file + page serving

**Goal:** confirm the completed session's video is served and the detail page renders.

```bash
curl -o /dev/null -w 'HTTP %{http_code} size=%{size_download}\n' \
  http://127.0.0.1:8765/media/sessions/<id>/reel.mp4
# → HTTP 200 size=2058122

curl -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8765/sessions/<id>
# → HTTP 200
```

Both served. ✅

---

## Things I deliberately did NOT verify

- **Langfuse tracing.** Compose stack written but not booted; tracing is an instrumentation
  layer, not on the critical path for producing a reel.
- **Multi-user concurrency.** Single-user hackathon scope.
- **Resumption preserving agent turns.** Pre-agent steps and assembly resume cleanly via
  `step_results`; the agent loop re-runs from scratch. Documented as a known limitation in
  the implementation summary.
- **Long videos (> 10 minutes).** Hard-rejected by `download_video` per the duration cap;
  not exercised.
- **Whisper fallback to local `faster-whisper`.** The HF endpoint worked first try with
  word timestamps, so the fallback path was never invoked.
- **Emotion-marker fidelity** in TTS output (plan §16 Q1). Requires human review of
  rendered avatar videos.

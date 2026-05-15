# ReelAgent — Demo Driver Knowledge Base

You are driving this demo. Use this document to know: what to instruct the operator to do, what to look for on screen to confirm it happened, and what to say to the audience while waiting.

---

## What ReelAgent Is (for audience narration)

ReelAgent turns any YouTube video into a short reaction reel (10–60 seconds) with a lip-synced AI character commentator. The entire creative process — picking the best moment, writing commentary, generating the character, assembling the video — is handled autonomously by an AI agent. The user only provides a URL.

---

## Demo Steps — Driver Playbook

### Step 1 — Homepage

**What you should see on screen:** A page with a URL input field, a Submit button, and the ReelAgent header.

**Instruct the operator:**
> "Go to the homepage — you should see a single input field. Paste the YouTube URL in there."

**Confirm on screen:** URL appears in the input field.

**Then instruct:**
> "Hit Submit."

**Confirm on screen:** Page redirects to a new URL like `/sessions/<id>`. The session detail page loads.

**Say to audience:**
> "The moment we hit Submit, ReelAgent creates a new session and starts working immediately. This is the session page — everything that happens next will appear here live."

---

### Step 2 — Pre-Agent Checklist (top of session page)

Watch the checklist at the top of the page. Three items will check off in sequence. Narrate each one as it happens.

#### ⬜ → ✅ Download Video
**What to watch for:** The "Download Video" item gets a checkmark or turns green.

**Say to audience:**
> "First step — it's downloading the full YouTube video using yt-dlp. Depending on the video length, this takes 15 to 30 seconds. It needs the full video, not just audio, because it will analyze the actual frames later."

**If it's taking more than 30 seconds:**
> "Larger videos take a bit longer here — still going, almost there."

#### ⬜ → ✅ Extract Audio
**What to watch for:** "Extract Audio" checks off — this happens fast, usually within a few seconds of the download completing.

**Say to audience:**
> "Audio extracted. That's the sound track pulled out separately so Whisper can transcribe it."

#### ⬜ → ✅ Transcribe
**What to watch for:** "Transcribe" checks off. This is the slowest pre-agent step — 20 to 60 seconds.

**Say to audience while waiting:**
> "Now Whisper is transcribing every word in the video with precise word-level timestamps. This matters because the agent uses those timestamps to find exactly which moment is most interesting to clip — it's not guessing, it's reading the actual transcript."

**When it checks off:**
> "Transcription done. The agent takes over now."

---

### Step 3 — Agent Loop (main section of session page)

**What to watch for:** A live feed appears below the checklist. You'll see "Thinking" blocks and tool call rows appearing in real time.

**Say to audience:**
> "The AI agent is live. Everything from here is autonomous — watch the feed."

#### Thinking Blocks (collapsible, labelled "Thinking")
**What to watch for:** A collapsible block appears with the agent's reasoning text.

**Say to audience:**
> "These are the agent's actual thoughts — it's reading the transcript right now, deciding which moment in the video is worth reacting to. You can expand these to see exactly what it's reasoning through."

#### Tool Calls — watch for these rows appearing:

---

**`get_frames`**
**What to watch for:** A tool call row labelled "get_frames" with a time window (e.g. 45s–90s).

**Say to audience:**
> "The agent is sampling frames from a specific section of the video and running a vision model over them. It's not just reading the transcript — it's actually looking at the footage to understand what's happening visually in that window."

---

**`generate_reaction_image`**
**What to watch for:** A "generate_reaction_image" row appears — it will spin for 15–30 seconds then show a result.

**Say to audience:**
> "Now it's generating a still reaction image using Runway's image model — this is the character's expression for this moment. It feeds into the animated clip next."

---

**`generate_animated_reaction`**
**What to watch for:** A "generate_animated_reaction" row — takes 30–60 seconds.

**Say to audience:**
> "This is the animated reaction clip. Runway's gen4.5 video model is generating a few seconds of the character actually moving and reacting. This takes about 30 to 60 seconds — it's generating real video frames, not a template."

---

**`generate_character_video`**
**What to watch for:** A "generate_character_video" row — takes 30–60 seconds.

**Say to audience:**
> "This is the centrepiece — Runway's GWM-1 avatar model is generating the character delivering the commentary script, fully lip-synced. The voice, the lip movement, all of it generated from the script the agent just wrote. Give it about 30 to 60 seconds."

---

**`generate_sound_effect`**
**What to watch for:** A "generate_sound_effect" row — usually fast, under 15 seconds.

**Say to audience:**
> "The agent decided the reel needs a sound effect here — it's generating one from a text description via ElevenLabs. This is back in under 15 seconds usually."

---

**`isolate_voice`**
**What to watch for:** A "isolate_voice" row — 10–20 seconds.

**Say to audience:**
> "Voice isolation — it's pulling a clip of the original video's audio and stripping background noise, leaving just the clean speech. That clip might appear in the final reel for context."

---

**`finalize_reel`**
**What to watch for:** A "finalize_reel" row appears. After this, no more tool calls — assembly begins.

**Say to audience:**
> "The agent just called finalize_reel — it's done making decisions. It submitted a complete production plan: every clip, every asset, in order, with exact timings. Assembly starts now."

---

### Step 4 — Assembly

**What to watch for:** A brief "Assembling" or similar status indicator. This is fast — 5 to 15 seconds.

**Say to audience:**
> "ffmpeg is stitching all the generated assets together into the final MP4. This part is quick — seconds, not minutes."

---

### Step 5 — Final Reel (the reveal)

**What to watch for:** A video player appears at the bottom of the session page with the finished reel.

**Instruct the operator:**
> "Click play on the video."

**Say to audience after it plays:**
> "That's it. A YouTube URL in, a finished reaction reel out. The agent picked the moment, wrote the script, generated every asset through Runway, and assembled that — fully automated. Start to finish, about two to three minutes."

---

## Timing Reference

| Stage | Typical Duration | What to say while waiting |
|---|---|---|
| Video download | 10–30 sec | Whisper transcription context |
| Audio extraction | 2–5 sec | Brief mention, move on |
| Transcription | 20–60 sec | Explain word-level timestamps |
| Each Runway tool call | 20–60 sec | Explain what the model is doing |
| Assembly | 5–15 sec | Brief mention |
| **Total** | **~2–5 min** | — |

**General waiting line:**
> "ReelAgent is doing genuine generative work here — every asset is created from scratch, not pulled from a library. That's why it takes a few minutes. What you get at the end is entirely original."

---

## If Something Looks Wrong on Screen

**Checklist item stuck for more than 60 seconds:**
> "This step is taking a moment — YouTube downloads can slow down on certain networks. It'll complete automatically, nothing to do on our end."

**Agent loop stops updating:**
> "The live feed uses server-sent events — if it looks frozen, a quick page refresh will backfill all missed events from the database. Nothing is lost."

**A tool call row shows an error:**
> "That tool call hit an issue — the agent will retry or route around it. Checkpointing means anything that already completed doesn't get re-run."

**Page doesn't redirect after Submit:**
> "Let's check the URL — go ahead and hit Submit again."

---

## Key Things to Highlight for the Audience

- **Fully autonomous** — the agent makes every creative decision. The user only provided a URL.
- **Real lip-sync** — the character video is generated by Runway's GWM-1 avatar model, not a loop or deepfake.
- **Agentic, not scripted** — the pipeline isn't a fixed sequence. The agent decides what tools to call and in what order based on what it observes.
- **Live transparency** — every reasoning step and tool call is visible in real time. Nothing is hidden.
- **Resumable** — if anything fails mid-way, the session resumes from the last checkpoint without re-running expensive steps.

# ReelAgent — AI Reaction Reel Generator

## What It Is

You paste a YouTube URL. An AI agent reads the transcript, finds the single most interesting moment, and produces a 20-second reaction reel — complete with a lip-synced character commentator — ready to post.

No editing. No prompting individual tools. One input, one output.

---

## The Problem It Solves

YouTube videos are long. Most of the value in a 10-minute video lives in 30 seconds. People share those moments, but sharing means either sending a timestamp ("watch from 4:32") or manually cutting a clip — neither of which produces something polished enough to post as a reel.

Existing highlight tools (Opus Clip, Munch) solve the clipping problem but not the content problem. They return a raw clip with no commentary, no framing, no personality. The output still requires a creator to record a reaction, write a caption, add audio. It is raw material, not a finished piece.

ReelAgent produces the finished piece. The output is a reel someone would actually watch and share — not a clip that still needs work.

---

## Who It Is For

- Anyone who watches a lot of YouTube and wants to share reactions without filming themselves
- Creators who want to comment on trending videos without setting up a camera
- People who want to build a reaction content presence without showing their face

---

## How It Works — From the User's Perspective

1. **Paste a YouTube URL** (video must be under 10 minutes)
2. **Optionally type a direction** — "focus on the controversial claim", "make it funny", "explain why this matters" — or leave it blank and let the agent decide
3. **Hit generate**
4. Wait roughly 2-3 minutes
5. **Receive a 20-second reel** as a downloadable video file

That is the entire user experience. Everything else happens inside the agent.

---

## The Architecture — How It Actually Works

### The Orchestrator

The heart of the system is a powerful OpenAI-compatible LLM (like gpt 5.4) acting as the sole orchestrator. It does not follow a fixed pipeline. Instead, it has a set of tools available to it — each one wrapping a Runway API — and it decides autonomously which tools to call, in what order, with what inputs, to produce the reel.

The orchestrator never sees the video directly. What it sees:
- The full timestamped transcript of the video
- The user's optional direction
- A description of each available tool and what it produces

It reasons through the problem from the transcript alone — but if it needs visual context at a specific moment (to write a better reaction image prompt, or to confirm a moment is visually interesting and not just verbally), it can call a tool to pull frames from the video at any timestamp range. The visual context is on demand, not pre-fed.

Every creative decision is made by the model reasoning from these inputs. No hard-coded steps dictate what it does next.

### The Full Pipeline

```
User: YouTube URL + optional direction ("roast it" / "explain why this matters")
          |
          v
yt-dlp: download audio stream only (faster than full video download)
          |
          v
Whisper: transcribe audio → full text with word-level timestamps
[video capped at 10 minutes, transcript fits in one context window]
          |
          v
Orchestrator (OpenAI-compatible LLM — gpt 5.4 or equivalent)
receives: transcript + timestamps + user direction + available tools
          |
          | ← makes all creative decisions here (see below)
          |
          v
Tool calls available to the orchestrator:
          |
          |---> get_frames(start_sec, end_sec, prompt)  [non-Runway, local]
          |         ffmpeg extracts frames from the downloaded video
          |         frames + prompt passed to a vision model internally
          |         returns: text answer only — raw images never reach the orchestrator
          |         keeps the main agent context lean
          |         e.g. prompt: "what is the person holding in this scene?"
          |              returns: "a document labelled X, held up to the camera"
          |         (optional — called only if orchestrator asks)
          |
          |---> generate_reaction_image(prompt)       [Runway]
          |         POST /v1/text_to_image
          |         returns: image URL
          |
          |---> generate_animated_reaction(prompt, duration) [Runway]
          |         POST /v1/text_to_video
          |         returns: task ID → poll → video URL
          |         short 2-4s animated clip — the video equivalent of a reaction GIF
          |         generated to match the moment (e.g. "cartoon head exploding",
          |         "money flying away", "record scratch freeze frame")
          |
          |---> generate_sound_effect(prompt, duration) [Runway]
          |         POST /v1/sound_effect
          |         returns: audio URL
          |
          |---> generate_character_video(script)      [Runway]
          |         POST /v1/avatar_videos
          |         script includes emotion markers (see below)
          |         returns: task ID → poll → video URL
          |
          |---> isolate_voice(clip_url)               [Runway]
                    POST /v1/voice_isolation
                    returns: clean audio URL

[Runway generation calls run in parallel after the plan is set]
          |
          v
ffmpeg: assemble final reel according to orchestrator's timing plan
          |
          v
Output: 20-second MP4, downloadable
```

### What the Orchestrator Actually Decides

This is where the intelligence lives. The orchestrator is not filling in slots in a template — it is making genuine editorial decisions:

**Decision 1 — Finding the moment**

It reads the full transcript and identifies one window worth reacting to. The quality of this decision determines the quality of the reel. What it looks for:

- A claim that is surprising, controversial, or factually questionable
- A line that lands as unintentionally funny
- A key reveal the rest of the video builds toward
- A take it can meaningfully push back on or affirm

It picks a specific start and end timestamp — typically 8-14 seconds — and reasons about why this moment is the right one. If the transcript alone is ambiguous (e.g. someone reacts strongly but the words don't explain why), the orchestrator can call `get_frames` with a targeted prompt — "what is the person reacting to on screen?" — and gets back a plain text answer. The raw frames never enter the orchestrator's context; only the vision model's text response does. That reasoning informs everything after.

**Decision 2 — Writing the commentary**

It writes a short script (spoken in 5-7 seconds) that is a reaction, not a summary. A take. "Here is why this is interesting / wrong / significant." The tone follows the user's direction, or the nature of the moment if no direction was given. The script must work as standalone audio — a viewer who has never seen the original video should understand the reel.

The script is written with **emotion markers** embedded inline. These tell the character how to deliver each line — not just what to say but how to say it:

```
[disbelief] He actually said this on camera.
[pause]
[laughing] Bro just casually dropped that like it's nothing.
[serious] But here's why this actually matters...
```

Supported markers cover the range of reaction emotions: `[shocked]`, `[laughing]`, `[disbelief]`, `[serious]`, `[sarcastic]`, `[excited]`, `[deadpan]`, `[pause]`. The orchestrator chooses markers that match the moment's tone — a controversial political take gets different emotional delivery than an absurd comedy moment. This is what makes the character feel like it is genuinely reacting rather than reading a script in a flat voice.

**Decision 3 — Designing the reel structure and calling tools**

The orchestrator designs the full 20-second reel by deciding what to generate and how to assemble it. It calls tools based on its own judgment:

- Does it want a static visual beat? It calls `generate_reaction_image` — a meme-style still image
- Does it want that beat to have motion? It calls `generate_animated_reaction` instead — a 2-4 second generated clip, the equivalent of a reaction GIF but created fresh for this exact moment
- Does it want an audio hit at a specific beat? It calls `generate_sound_effect`
- It always calls `generate_character_video` with the commentary script (with emotion markers)
- It always calls `isolate_voice` on the original clip to clean the audio

The orchestrator also decides the assembly plan:
- Which segments of the original clip to use and in what order
- When to mute original audio vs keep it
- Exact timestamps where each generated asset appears
- Whether the character is in the corner or takes the full frame at each point

A slow-burn controversial claim gets a different structure than a sudden absurd blurt. The orchestrator matches the structure to the moment.

---

## The Output Reel — What It Actually Looks Like

A typical 20-second reel assembled from the agent's plan:

```
0 - 2s   Original clip plays — cold open, no introduction
          Character visible in bottom corner, silent

2 - 9s   Clip continues, character reacts in corner
          Original audio: ON (viewer hears what was said)

9 - 11s  Hard cut to generated reaction image
          Sound effect sting hits on the cut
          Original audio: OFF

11 - 14s Original clip resumes, key line plays again
          Original audio: ON, character still in corner

14 - 20s Character takes full commentary
          Lip-synced, speaks directly to camera
          Original clip shrinks to corner
```

This is not fixed. A different moment might have the character speaking earlier, or no reaction image at all, or two sound effect hits. The structure comes from the agent's plan.

The character is a lip-synced avatar — not a static portrait, not a voiceover. The viewer sees a face speaking the commentary with matching mouth movement, exactly like a person filming a reaction video.

---

## Runway's Role — APIs as Tools the Orchestrator Calls

Runway APIs are not a fixed pipeline here — they are tools available to the orchestrator on demand. The orchestrator decides whether to call each one, when, and with what prompt. It can call them in any combination based on what the moment calls for.

| Tool | Source | What It Produces | When Called |
|------|--------|-----------------|-------------|
| `get_frames(start, end, prompt)` | local ffmpeg + vision model | Extracts frames, runs them through a vision model with the given prompt, returns **text only** back to the orchestrator. Raw images never enter the main context. e.g. `prompt="what is the person reacting to visually?"` → `"a graph showing a 90% drop"` | Optional — when the orchestrator needs visual context the transcript alone doesn't give |
| `generate_character_video(script)` | `POST /v1/avatar_videos` | Lip-synced video of the character delivering the commentary. Script includes emotion markers for expressive delivery. | Always |
| `isolate_voice(clip_url)` | `POST /v1/voice_isolation` | Clean audio from the original clip, background noise removed | Always |
| `generate_reaction_image(prompt)` | `POST /v1/text_to_image` | A visual beat — meme-style image, reaction face, bold text card | When the orchestrator wants a punchy static visual cut |
| `generate_animated_reaction(prompt, duration)` | `POST /v1/text_to_video` | A short 2-4 second animated clip — the video equivalent of a reaction GIF, generated to match the moment. e.g. "cartoon head exploding", "money flying away dramatically", "spinning newspaper with breaking news". Motion makes it land harder than a static image. | When the beat needs motion, not just a still |
| `generate_sound_effect(prompt, duration)` | `POST /v1/sound_effect` | An audio sting — dramatic reverb, record scratch, comedic hit | When the orchestrator wants audio punctuation at a beat |

`get_frames` is the only tool that may run before the plan is finalised — it gives the orchestrator visual information to reason with. All Runway calls run in parallel once the plan is set.

---

## Constraints and Scope (for the hackathon)

- One reel per submission (not batch)
- YouTube videos under 10 minutes
- One moment per reel (the agent picks the best one)
- 20 seconds maximum reel length
- Single character persona (can be configured before use)

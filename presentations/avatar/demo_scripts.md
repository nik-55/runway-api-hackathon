# Demo Clip Scripts

Four clips total. All pre-generated, saved to `media/demo/clips/clip1.mp4` through `clip4.mp4`. Press Space on the `/demo` page to advance each clip.

---

## Clip 1 — Intro & Homepage

Hey everyone! Welcome — really excited to show you this today.
What you're about to see is ReelAgent. You paste a YouTube URL, and an AI agent turns it into a fully edited reaction reel — complete with a lip-synced character commentator reacting to the best moment in the video. The agent uses RunwayML tools to generate every asset — the character video, the reaction visuals, the sound design — and assembles it all automatically.
The agent makes every creative decision itself — what moment to clip, what the character should say, how the reel is put together. We're going to watch it do that live right now.
Let's start.

This is the entire interface. One input field — a YouTube URL. That's it.
We're submitting now.

**Save as:** `media/demo/clips/clip1.mp4`

---

## Clip 2 — Session page

We're on the session page now. The pipeline starts automatically — downloading the video, extracting audio, running transcription. Then the agent takes over.
Give it a moment — I'll be back once it's done.

**Save as:** `media/demo/clips/clip2.mp4`

---

## Clip 3 — Post-processing summary

While that was running — here's exactly what happened.

ReelAgent downloaded the full video and ran it through Whisper, transcribing every word with precise timestamps. That transcript is what the agent reads to find the most interesting moment — not just the loudest or the longest, but the most worth reacting to.

Then the agent took over completely. It reasoned through the transcript, sampled actual video frames to understand what was happening visually, and wrote a commentary script from scratch. Then it called Runway — generating the lip-synced character video, the reaction visuals, the sound design. Every asset created from nothing, not pulled from a template.

Once it had everything, it submitted a production plan and ffmpeg assembled the final cut automatically. No human made a single creative decision in that pipeline. Here's what it produced.

**Save as:** `media/demo/clips/clip3.mp4`

---

## Clip 4 — Reveal

That's a finished reaction reel — from a single YouTube URL, fully automated, start to finish.
The agent picked the moment, wrote the script, generated every asset through Runway, and assembled that. ReelAgent.

**Save as:** `media/demo/clips/clip4.mp4`

---

## Generation order

Generate all 4 clips upfront using `generate_character_video`, save to `media/demo/clips/clip1.mp4` through `clip4.mp4`. Then open `/demo` and record.

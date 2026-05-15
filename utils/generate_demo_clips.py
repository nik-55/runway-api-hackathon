#!/usr/bin/env python3
"""Generate all 5 demo clips and save to media/demo/clips/."""

import sys
import os
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.agent.runway_client import get_client

CLIPS = [
    (
        "clip1.mp4",
        """Hey everyone! Welcome — really excited to show you this today.
What you're about to see is ReelAgent. You paste a YouTube URL, and an AI agent turns it into a fully edited reaction reel — complete with a lip-synced character commentator reacting to the best moment in the video. No prompting, no editing, nothing else. Just a URL in, a finished video out.
The agent makes every creative decision itself — what moment to clip, what the character should say, how the reel is put together. We're going to watch it do that live right now.
Let's start.""",
    ),
    (
        "clip2.mp4",
        """This is the entire interface. One input field — a YouTube URL. That's it. No settings, no parameters, no prompt engineering required.
We're submitting now.""",
    ),
    (
        "clip3.mp4",
        """We're on the session page now. The pipeline starts automatically — downloading the video, extracting audio, running transcription. Then the agent takes over.
Give it a moment — I'll be back once it's done.""",
    ),
    (
        "clip4.mp4",
        """While that was running — here's exactly what happened.

ReelAgent downloaded the full video and ran it through Whisper, transcribing every word with precise timestamps. That transcript is what the agent reads to find the most interesting moment — not just the loudest or the longest, but the most worth reacting to.

Then the agent took over completely. It reasoned through the transcript, sampled actual video frames to understand what was happening visually, and wrote a commentary script from scratch. Then it called Runway — generating the lip-synced character video, the reaction visuals, the sound design. Every asset created from nothing, not pulled from a template.

Once it had everything, it submitted a production plan and ffmpeg assembled the final cut automatically. No human made a single creative decision in that pipeline. Here's what it produced.""",
    ),
    (
        "clip5.mp4",
        """That's a finished reaction reel — from a single YouTube URL, fully automated, start to finish.
The agent picked the moment, wrote the script, generated every asset through Runway, and assembled that. ReelAgent.""",
    ),
]

AVATAR_ID = settings.character_avatar_preset  # 96af6db1-6e10-40da-b10d-8e712a826111
VOICE = settings.character_voice_preset        # morgan
OUT_DIR = settings.media_root / "demo" / "clips"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def generate(filename: str, script: str) -> None:
    out_path = OUT_DIR / filename
    print(f"\n--- {filename} ---")
    print(f"Script ({len(script)} chars): {script[:80]}...")

    client = get_client()
    print("Submitting to Runway...")
    task = client.avatar_videos.create(
        model="gwm1_avatars",
        avatar={"type": "custom", "avatarId": AVATAR_ID},
        speech={
            "type": "text",
            "text": script,
            "voice": {"type": "preset", "presetId": VOICE},
        },
    ).wait_for_task_output()

    output = getattr(task, "output", None) or []
    if not output:
        print(f"ERROR: no output for {filename}, task_id={getattr(task, 'id', None)}")
        return

    url = output[0]
    print(f"Downloading from {url[:60]}...")
    urllib.request.urlretrieve(url, str(out_path))
    size_mb = out_path.stat().st_size / 1_000_000
    print(f"Saved {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    print(f"Avatar: {AVATAR_ID}")
    print(f"Voice:  {VOICE}")
    print(f"Output: {OUT_DIR}")

    for fname, script in CLIPS:
        generate(fname, script)

    print("\nAll clips generated.")

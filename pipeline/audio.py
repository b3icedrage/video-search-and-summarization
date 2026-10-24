"""Audio / Voice Layer.

Honest scope: NVIDIA's hosted audio models do ASR (Canary) and speech (Magpie/
Riva TTS) - they do not synthesize squeaks or squish SFX. So this layer emits a
structured SFX plan (descriptions written by the Director) and optionally
renders voiceover narration through Magpie TTS when --narrate is passed.
"""

from __future__ import annotations

import json
import os

import requests

from . import config


def sfx_plan(storyboard: dict) -> list[dict]:
    """Flatten every shot's SFX into a cue sheet."""
    cues = []
    offset = 0.0
    for shot in storyboard["shots"]:
        duration = float(shot.get("duration_sec", 3))
        for cue in shot.get("sfx", []):
            cues.append(
                {
                    "shot": shot["id"],
                    "at_sec": round(offset, 2),
                    "name": cue.get("name", "sfx"),
                    "description": cue.get("description", ""),
                    # Library hook: drop a matching file here later and composite picks it up.
                    "file": f"audio/sfx/{shot['id']}_{cue.get('name', 'sfx')}.wav",
                }
            )
        offset += duration
    return cues


def write_sfx_plan(storyboard: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "sfx_plan.json")
    with open(path, "w") as fh:
        json.dump(sfx_plan(storyboard), fh, indent=2)
    return path


def narrate(storyboard: dict, out_dir: str, live: bool) -> str | None:
    """Optional voiceover via Magpie TTS. Returns the wav path or None."""
    if not live:
        return None
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "narration.wav")
    resp = requests.post(
        config.TTS_URL,
        headers=config.headers(),
        data={
            "text": storyboard.get("narration", storyboard.get("title", "")),
            "language": "en-US",
            "voice": config.TTS_VOICE,
            "encoding": "LINEAR_PCM",
            "sample_rate_hz": "44100",
        },
        timeout=config.TIMEOUT,
    )
    resp.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return path

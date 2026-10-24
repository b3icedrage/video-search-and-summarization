#!/usr/bin/env python3
"""NIM Studio CLI: storyboard -> stills -> sound -> motion.

    python run_pipeline.py "a slime monster discovers ramen"          # offline dry-run
    NVIDIA_API_KEY=nvapi-... python run_pipeline.py "..." --live      # real calls
    NVIDIA_API_KEY=nvapi-... python run_pipeline.py "..." --live --narrate

With no NVIDIA_API_KEY set the pipeline runs in dry-run mode automatically:
the Director returns a canned storyboard and frames are placeholders, so the
whole path (including the FFmpeg composite) is testable for free.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from pipeline import audio, composite, director, visual
from pipeline import config


def main() -> int:
    parser = argparse.ArgumentParser(description="Storyboard -> stills -> sound -> motion on NVIDIA NIM")
    parser.add_argument("concept", help="One-line idea for the clip")
    parser.add_argument("--out", default="out", help="Output directory (default: out)")
    parser.add_argument("--live", action="store_true", help="Force real API calls (requires NVIDIA_API_KEY)")
    parser.add_argument("--dry-run", action="store_true", help="Force offline mode")
    parser.add_argument("--narrate", action="store_true", help="Also render voiceover narration via TTS")
    parser.add_argument("--model", help="Override the director model ID")
    parser.add_argument("--image-model", help="Override the image model ID")
    args = parser.parse_args()

    if args.model:
        config.DIRECTOR_MODEL = args.model
    if args.image_model:
        config.IMAGE_MODEL = args.image_model

    if args.live and not config.API_KEY:
        parser.error("--live requires NVIDIA_API_KEY in the environment")
    live = (bool(config.API_KEY) or args.live) and not args.dry_run

    print(f"[0/4] mode     : {'LIVE' if live else 'DRY RUN (no API key)'}")
    print(f"       director : {config.DIRECTOR_MODEL}")
    print(f"       visual   : {config.IMAGE_MODEL}")

    print("[1/4] Director: generating storyboard ...")
    storyboard = director.generate_storyboard(args.concept) if live else director.sample_storyboard(args.concept)
    os.makedirs(args.out, exist_ok=True)
    sb_path = os.path.join(args.out, "storyboard.json")
    with open(sb_path, "w") as fh:
        json.dump(storyboard, fh, indent=2)
    print(f"        -> {sb_path} ({len(storyboard['shots'])} shots: {storyboard['title']})")

    print("[2/4] Visual: rendering one still per shot ...")
    frames = visual.render_frames(storyboard, os.path.join(args.out, "frames"), live=live)
    for f in frames:
        print(f"        -> {f['path']}  [{f['source']}]")

    print("[3/4] Audio: writing SFX cue sheet ...")
    plan_path = audio.write_sfx_plan(storyboard, os.path.join(args.out, "audio"))
    print(f"        -> {plan_path} ({sum(len(s.get('sfx', [])) for s in storyboard['shots'])} cues)")
    narration = None
    if args.narrate:
        if live:
            narration = audio.narrate(storyboard, os.path.join(args.out, "audio"), live=True)
            print(f"        -> {narration}")
        else:
            print("        -> skipped (narration needs --live + NVIDIA_API_KEY)")

    print("[4/4] Composite: stitching with FFmpeg ...")
    out_video = os.path.join(args.out, "clip.mp4")
    ok, msg = composite.render(storyboard, frames, narration, out_video)
    print(f"        -> {'OK ' + msg if ok else msg}")

    print("\nDone." + ("  (dry run - set NVIDIA_API_KEY and re-run with --live for real output)" if not live else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

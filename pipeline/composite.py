"""Animation Composite: stills -> motion with FFmpeg.

Full video diffusion is skipped on purpose: each shot still gets a camera move
(zoompan) and shots are cross-faded together, with narration mixed on top.
If ffmpeg is missing, a ready-to-run command script is written instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess

FPS = 24
SIZE = "1280x720"
XFADE = 0.4  # seconds of cross-fade between shots


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _pan_expr(camera: str, idx: int) -> str:
    """Slow push-in by default; alternate pan direction per shot for variety."""
    if "pull" in camera:
        return "max(1.2-0.0012*in,1.0)"
    if "pan" in camera:
        return f"1.05+0.0004*in"
    if "orbit" in camera or "spin" in camera:
        return "1.08"
    if "zoom" in camera:
        return "min(1.0+0.003*in,1.35)"
    return "min(1.0+0.0012*in,1.2)"


def build_command(storyboard: dict, frames: list[dict], narration: str | None, out_path: str) -> list[str]:
    """Pure function: returns the ffmpeg argv (also written out as a script)."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    filters, labels = [], []
    durations = [float(s.get("duration_sec", 3)) for s in storyboard["shots"]]

    for i, (shot, frame) in enumerate(zip(storyboard["shots"], frames)):
        cmd += ["-loop", "1", "-t", str(durations[i]), "-i", frame["path"]]
        zexpr = _pan_expr(shot.get("camera", ""), i)
        filters.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            f"zoompan=z='{zexpr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={SIZE}:fps={FPS}[v{i}]"
        )
        labels.append(f"[v{i}]")

    # Chain shots with cross-fades.
    prev = labels[0]
    offset = 0.0
    for i in range(1, len(labels)):
        offset += durations[i - 1] - XFADE
        out = f"[x{i}]"
        filters.append(
            f"{prev}{labels[i]}xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{out}"
        )
        prev = out
    filters.append(f"{prev}concat=n=1:v=1:a=0[vcat]")
    # xfade output has no audio pad; add silent track when narration exists.
    map_args = ["-map", "[vcat]"]
    if narration:
        # Narration becomes the last input; trim/pad it to the video length.
        n = len(frames)
        total = sum(durations) - XFADE * (len(durations) - 1)
        cmd += ["-i", narration]
        filters.append(
            f"[{n}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={total:.3f}[acat]"
        )
        map_args = ["-map", "[vcat]", "-map", "[acat]"]

    cmd += ["-filter_complex", ";".join(filters), *map_args,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-movflags", "+faststart", out_path]
    return cmd


def render(storyboard: dict, frames: list[dict], narration: str | None, out_path: str) -> tuple[bool, str]:
    """Composite the video. Returns (ok, message)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cmd = build_command(storyboard, frames, narration, out_path)
    script_path = os.path.splitext(out_path)[0] + "_ffmpeg.sh"
    with open(script_path, "w") as fh:
        fh.write("#!/bin/sh\n" + " ".join(f"'{c}'" if " " in c else c for c in cmd) + "\n")

    if not _ffmpeg_available():
        return False, f"ffmpeg not installed - run {script_path} on a machine that has it"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"ffmpeg failed: {proc.stderr.strip()[-500:]}"
    return True, out_path

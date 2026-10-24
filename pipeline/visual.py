"""Visual Generation Layer: SDXL / FLUX.1 via NVIDIA endpoints, one still per shot.

--dry-run draws placeholder frames with PIL so the rest of the pipeline can be
exercised without a key.
"""

from __future__ import annotations

import base64
import os

import requests
from PIL import Image, ImageDraw

from . import config

FRAME_SIZE = (1280, 720)


def _payload(prompt: str, seed: int) -> dict:
    """Two hosted families, two payload shapes."""
    if "sdxl" in config.IMAGE_MODEL.lower() or "stable-diffusion" in config.IMAGE_MODEL.lower():
        return {
            "text_prompts": [{"text": prompt, "weight": 1}, {"text": "", "weight": -1}],
            "cfg_scale": 5,
            "steps": 25,
            "seed": seed,
        }
    return {"prompt": prompt, "steps": 20, "seed": seed}


def _decode_response(resp: requests.Response) -> bytes:
    """Hosted response schema is not fully documented: accept every known shape."""
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if ctype.startswith("image/"):
        return resp.content
    data = resp.json()
    if isinstance(data, dict):
        if data.get("artifacts"):
            return base64.b64decode(data["artifacts"][0].get("base64", ""))
        if data.get("data"):
            item = data["data"][0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"])
            if item.get("url"):
                return requests.get(item["url"], timeout=config.TIMEOUT).content
    raise ValueError(f"Unrecognized image response: {str(data)[:200]}")


def _placeholder(shot: dict, path: str) -> None:
    img = Image.new("RGB", FRAME_SIZE, (16, 20, 24))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, FRAME_SIZE[0] - 40, FRAME_SIZE[1] - 40], outline=(118, 185, 0), width=3)
    draw.text((70, 70), shot["id"].upper(), fill=(118, 185, 0))
    draw.text((70, 110), shot.get("scene", "")[:80], fill=(200, 210, 220))
    for i, line in enumerate(_wrap(shot.get("visual_prompt", ""), 70)[:9]):
        draw.text((70, 170 + i * 22), line, fill=(120, 135, 150))
    draw.text((70, FRAME_SIZE[1] - 80), "DRY RUN placeholder (no API key)", fill=(90, 100, 110))
    img.save(path)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def render_frames(storyboard: dict, out_dir: str, live: bool) -> list[dict]:
    """Render one still per shot. Returns [{'shot': id, 'path': ..., 'source': ...}]."""
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    for i, shot in enumerate(storyboard["shots"]):
        path = os.path.join(out_dir, f"{shot['id']}.png")
        if not live:
            _placeholder(shot, path)
            frames.append({"shot": shot["id"], "path": path, "source": "placeholder"})
            continue
        resp = requests.post(
            f"{config.IMAGE_BASE}/{config.IMAGE_MODEL}",
            headers={**config.headers(), "Content-Type": "application/json"},
            json=_payload(shot["visual_prompt"], seed=i),
            timeout=config.TIMEOUT,
        )
        image_bytes = _decode_response(resp)
        # The model returns JPEG regardless of the extension we picked — name it right.
        ext = ".png" if image_bytes[:4] == b"\x89PNG" else ".jpg"
        path = os.path.join(out_dir, f"{shot['id']}{ext}")
        with open(path, "wb") as fh:
            fh.write(image_bytes)
        frames.append({"shot": shot["id"], "path": path, "source": config.IMAGE_MODEL})
    return frames

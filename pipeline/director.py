"""Director Layer: Llama-3.3 / Nemotron generates the structured JSON storyboard."""

from __future__ import annotations

import json
import re

import requests

from . import config

SYSTEM_PROMPT = (
    "You are a film director and concept artist. You convert a short idea into a "
    "shot-by-shot storyboard for a short animated clip. You answer with a single "
    "JSON object and nothing else."
)

USER_PROMPT_TEMPLATE = """\
Idea: {concept}

Return a JSON object with exactly this shape:
{{
  "title": "short clip title",
  "style": "one-line art direction used to keep every shot visually consistent",
  "narration": "1-2 sentence voiceover line for the whole clip",
  "shots": [
    {{
      "id": "shot_01",
      "duration_sec": 3,
      "scene": "what happens",
      "camera": "camera move, e.g. slow push-in",
      "visual_prompt": "a self-contained Stable Diffusion / FLUX prompt for this shot, "
                       "repeating the style so frames stay consistent",
      "sfx": [
        {{"name": "squish", "description": "wet, rubbery squish with a small pop"}}
      ]
    }}
  ]
}}

Rules: 4 to 6 shots, durations 2-5 seconds, every visual_prompt repeats the style
string verbatim, each shot has 1-3 sfx entries with concrete sound descriptions."""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating code fences."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Director returned no JSON: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def generate_storyboard(concept: str) -> dict:
    """Live call to the Director model. Returns the parsed storyboard dict."""
    payload = {
        "model": config.DIRECTOR_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(concept=concept)},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(
        f"{config.CHAT_BASE}/chat/completions",
        headers={**config.headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=config.TIMEOUT,
    )
    if resp.status_code == 400 and "response_format" in resp.text:
        payload.pop("response_format")  # model does not support JSON mode
        resp = requests.post(
            f"{config.CHAT_BASE}/chat/completions",
            headers={**config.headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=config.TIMEOUT,
        )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(content)


def sample_storyboard(concept: str) -> dict:
    """Offline storyboard used by --dry-run so the pipeline runs with no key."""
    style = "3D cartoon render, soft studio lighting, saturated colors, clay-shaded"
    shots = []
    beats = [
        ("A curious blob peeks out from behind a giant mushroom", "slow push-in",
         [("boing", "soft rubbery boing as it leans out"),
          ("sniff", "two quick curious sniffs")]),
        ("The blob spots a bowl of glowing noodles", "pan right",
         [("rumble", "low cartoon stomach rumble"),
          ("shimmer", "bright glassy sparkle shimmer")]),
        ("It lunges and slurps, cheeks bulging", "quick zoom-in",
         [("slurp", "long wet noodle slurp"),
          ("squeak", "high happy mouth squeak")]),
        ("It spins happily as noodle steam swirls", "orbit left",
         [("giggle", "rapid little giggle squeaks"),
          ("hiss", "soft steam hiss with a sizzle tail")]),
        ("Final pose: full belly, triumphant wave", "pull back",
         [("sigh", "warm satisfied sigh"),
          ("pop", "single tiny pop on the wave")]),
    ]
    for i, (scene, camera, sfx) in enumerate(beats, 1):
        shots.append(
            {
                "id": f"shot_{i:02d}",
                "duration_sec": 3,
                "scene": scene,
                "camera": camera,
                "visual_prompt": (
                    f"{scene}, {style}, {concept}, consistent character design, "
                    "wide shot, high detail"
                ),
                "sfx": [
                    {"name": n, "description": d} for n, d in sfx
                ],
            }
        )
    return {
        "title": f"Dry-run storyboard: {concept[:60]}",
        "style": style,
        "narration": f"An untold tale of {concept[:80]}.",
        "shots": shots,
        "offline": True,
    }

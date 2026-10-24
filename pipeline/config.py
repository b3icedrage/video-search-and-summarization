"""Endpoint + model configuration.

Everything is swappable via environment variables, which is the actual
"endpoint swapping" workflow: pick a model on build.nvidia.com, copy its ID,
set it here (or export it before running).

    DIRECTOR_MODEL=meta/llama-3.1-70b-instruct python run_pipeline.py "..."

One nvapi-... key from build.nvidia.com works as a Bearer token for every
call the pipeline makes.
"""

import os

API_KEY = os.environ.get("NVIDIA_API_KEY", "")

# Chat models (OpenAI-compatible). Used by the Director layer.
CHAT_BASE = os.environ.get("NIM_CHAT_BASE", "https://integrate.api.nvidia.com/v1")
DIRECTOR_MODEL = os.environ.get("DIRECTOR_MODEL", "meta/llama-3.2-11b-vision-instruct")
# NOTE: the hosted catalog rotates. Probe GET {CHAT_BASE}/models with your key
# before choosing; many familiar IDs now 404 or hang for a given account.

# Image models live on a different route family than chat.
IMAGE_BASE = os.environ.get("NIM_IMAGE_BASE", "https://ai.api.nvidia.com/v1/genai")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "black-forest-labs/flux.1-dev")
# flux.1-dev requires steps >= 5 (payload built in visual._payload)

# Optional narration (speech only; SFX stay as written descriptions).
TTS_URL = os.environ.get(
    "NIM_TTS_URL",
    "https://877104f7-e885-42b9-8de8-f6e4c6303969."
    "invocation.api.nvcf.nvidia.com/v1/audio/synthesize",
)
TTS_VOICE = os.environ.get("TTS_VOICE", "Magpie-Multilingual.EN-US.Aria")

TIMEOUT = int(os.environ.get("NIM_TIMEOUT", "120"))


def headers() -> dict:
    if not API_KEY:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set. Export it (export NVIDIA_API_KEY=nvapi-...) "
            "or run with --dry-run to exercise the pipeline offline."
        )
    return {"Authorization": f"Bearer {API_KEY}"}

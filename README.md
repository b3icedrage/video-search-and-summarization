# video-search-and-summarization

**NIM Studio** — a full runnable pipeline that turns a one-line idea into a short
animated clip, using only NVIDIA NIM endpoints, all swappable from config:

```
idea  →  [1] Director (LLM storyboard JSON)
      →  [2] Visual (SDXL / FLUX.1 stills, one per shot)
      →  [3] Audio (SFX cue sheet + optional TTS narration)
      →  [4] Composite (FFmpeg zoompan + cross-fades → clip.mp4)
```

## Quickstart (no API key needed)

```sh
pip install -r requirements.txt   # requests + Pillow
# ffmpeg must be on PATH for the composite step

python run_pipeline.py "a curious slime monster discovers a ramen shop"
```

With no `NVIDIA_API_KEY` set, the run is an automatic **dry-run**: the Director
returns a canned storyboard, frames are labeled placeholders, and FFmpeg still
stitches a real `out/clip.mp4` — so the whole path is testable for free.

## Going live

Get a free `nvapi-...` key from [build.nvidia.com](https://build.nvidia.com),
then:

```sh
export NVIDIA_API_KEY=nvapi-...
python run_pipeline.py "your idea" --live              # storyboard + stills
python run_pipeline.py "your idea" --live --narrate    # + voiceover TTS
```

### Swapping endpoints / models

This is the real "endpoint swapping" step — change model IDs in code config or
via env vars, nothing else:

| Layer   | Endpoint | Default model | Override |
|---------|----------|---------------|----------|
| Director | `integrate.api.nvidia.com/v1/chat/completions` | `meta/llama-3.2-11b-vision-instruct` | `DIRECTOR_MODEL`, or `--model` |
| Visual   | `ai.api.nvidia.com/v1/genai/{model}` | `black-forest-labs/flux.1-dev` | `IMAGE_MODEL`, or `--image-model` |
| Audio    | NVCF `…/v1/audio/synthesize` (Magpie TTS) | `Magpie-Multilingual.EN-US.Aria` | `NIM_TTS_URL`, `TTS_VOICE` |

**The hosted catalog rotates — probe before you pick.** `GET /v1/models` on the
chat base with your key lists what *might* exist, but many IDs are listed while
being unroutable for a given account: they either 404 (`Function … Not found for
account`) or silently hang. Proven live on a fresh key (Oct 2026): `meta/llama-3.2-11b-vision-instruct`,
`openai/gpt-oss-20b`, `minimaxai/minimax-m3.1-flash`, `meta/muse-glimmer-30b`,
and `black-forest-labs/flux.1-dev` (image, `steps >= 5`, returns
`artifacts[0].base64`). Proven dead: `meta/llama-3.3-70b-instruct`,
`meta/llama-3.1-8b-instruct` (410 EOL), `meta/llama-3.2-90b-vision-instruct`
(hangs), SDXL and `flux.1-schnell` (404/hang).

## Honest scope notes

- **SFX are descriptions, not audio.** NVIDIA's hosted audio models do ASR
  (Canary) and speech (Magpie/Riva TTS) — none synthesize squeaks or squish
  sounds. The Director writes concrete SFX cues to `out/audio/sfx_plan.json`
  with a `file` path each; drop matched WAVs there and extend
  `composite.render` to mix them in.
- **Narration is optional** (`--narrate`, live only): one voiceover line via
  Magpie TTS, trimmed/padded to the clip length.
- **No video diffusion.** Character states are generated as stills, then given
  camera motion (`zoompan`) and stitched with cross-fades — the standard
  lightweight composite workflow.

## Outputs

```
out/storyboard.json        structured storyboard (shots, prompts, sfx, narration)
out/frames/shot_0N.png     one still per shot
out/audio/sfx_plan.json    SFX cue sheet with timestamps
out/audio/narration.wav    voiceover (only with --live --narrate)
out/clip.mp4               final clip (out/clip_ffmpeg.sh is the raw command)
```

## Website

`index.html` is a self-contained single file (no build step) with the pipeline
architecture and a browser playground that can call the Director endpoint
directly if you paste a key — open it or hit the preview.

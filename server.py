#!/usr/bin/env python3
"""NIM Studio site server: static files + same-origin AI proxy.

The website runs the AI through /api/* on this server, so the NVIDIA key
stays in the workspace environment and never reaches the browser. A key
typed into the site's optional key field is forwarded as an override.

    python3 server.py [port]      # default 8080 (or $PORT)
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHAT_BASE = os.environ.get("NIM_CHAT_BASE", "https://integrate.api.nvidia.com/v1")
IMAGE_BASE = os.environ.get("NIM_IMAGE_BASE", "https://ai.api.nvidia.com/v1/genai")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "black-forest-labs/flux.1-dev")
TTS_URL = os.environ.get(
    "NIM_TTS_URL",
    "https://877104f7-e885-42b9-8de8-f6e4c6303969."
    "invocation.api.nvcf.nvidia.com/v1/audio/synthesize",
)
TTS_VOICE = os.environ.get("TTS_VOICE", "Magpie-Multilingual.EN-US.Aria")
API_KEY = os.environ.get("NVIDIA_API_KEY", "")

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 180  # upstream can be slow under load
MAX_BODY = 4 * 1024 * 1024
STATIC_FILES = {"", "index.html", "README.md"}  # what GET will serve


def _forward(url: str, key: str, data: bytes, content_type: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": content_type,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except Exception as exc:  # timeout, DNS, TLS...
        body = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()
        return 502, "application/json", body


class Handler(BaseHTTPRequestHandler):
    server_version = "NIMStudio/1.0"

    # ---------- helpers ----------
    CORS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    def _json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in self.CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, status: int, data: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in self.CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for k, v in self.CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def _auth(self) -> str | None:
        """Client override if the site sent one, else the server key."""
        supplied = self.headers.get("Authorization", "")
        if supplied.startswith("Bearer nvapi-"):
            return supplied.split(" ", 1)[1].strip()
        return API_KEY or None

    def _body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return None

    # ---------- static ----------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].lstrip("/")
        if path == "":
            path = "index.html"
        if path not in STATIC_FILES:
            self._json(404, {"error": "not found"})
            return
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            self._bytes(200, fh.read(), ctype)

    # ---------- AI proxy ----------
    def do_POST(self) -> None:  # noqa: N802
        key = self._auth()
        if not key:
            self._json(503, {"error": "server has no API key configured and none was supplied"})
            return
        payload = self._body()
        if payload is None:
            self._json(400, {"error": "invalid JSON body"})
            return

        if self.path == "/api/storyboard":
            fwd = {
                "model": payload.get("model") or os.environ.get(
                    "DIRECTOR_MODEL", "meta/llama-3.2-11b-vision-instruct"
                ),
                "messages": payload.get("messages", []),
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            }
            status, ctype, data = _forward(
                f"{CHAT_BASE}/chat/completions", key,
                json.dumps(fwd).encode(), "application/json",
            )
            if status == 400 and b"response_format" in data:
                fwd.pop("response_format")
                status, ctype, data = _forward(
                    f"{CHAT_BASE}/chat/completions", key,
                    json.dumps(fwd).encode(), "application/json",
                )
            self._bytes(status, data, ctype or "application/json")

        elif self.path == "/api/image":
            fwd = {
                "prompt": payload.get("prompt", ""),
                "steps": int(payload.get("steps", 20)),
                "seed": int(payload.get("seed", 0)),
            }
            status, _, data = _forward(
                f"{IMAGE_BASE}/{IMAGE_MODEL}", key,
                json.dumps(fwd).encode(), "application/json",
            )
            if status != 200:
                self._bytes(status, data, "application/json")
                return
            # Hosted schema: artifacts[0].base64 (verified live) with fallbacks.
            try:
                obj = json.loads(data)
                if obj.get("artifacts"):
                    import base64

                    data = base64.b64decode(obj["artifacts"][0].get("base64", ""))
                elif obj.get("data") and obj["data"][0].get("b64_json"):
                    import base64

                    data = base64.b64decode(obj["data"][0]["b64_json"])
                else:
                    self._json(502, {"error": "unrecognized image response shape"})
                    return
            except (ValueError, KeyError, IndexError):
                self._json(502, {"error": "could not decode image response"})
                return
            # The model returns JPEG despite the extension everyone expects — sniff it.
            if data[:4] == b"\x89PNG":
                ctype = "image/png"
            elif data[:3] == b"\xff\xd8\xff":
                ctype = "image/jpeg"
            else:
                ctype = "application/octet-stream"
            self._bytes(200, data, ctype)

        elif self.path == "/api/tts":
            text = str(payload.get("text", ""))[:2000]
            boundary = "----nimsudio7f3a"
            parts = [
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n{text}\r\n",
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nen-US\r\n",
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"\r\n\r\n{TTS_VOICE}\r\n",
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"encoding\"\r\n\r\nLINEAR_PCM\r\n",
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"sample_rate_hz\"\r\n\r\n44100\r\n",
                f"--{boundary}--\r\n",
            ]
            body = "".join(parts).encode()
            status, _, data = _forward(
                TTS_URL, key, body, f"multipart/form-data; boundary={boundary}"
            )
            if status != 200:
                self._bytes(status, data, "application/json")
                return
            self._bytes(200, data, "audio/wav")

        else:
            self._json(404, {"error": "unknown endpoint"})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8080))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    mode = "server key" if API_KEY else "NO KEY (site key field required)"
    print(f"NIM Studio site on 0.0.0.0:{port}  ·  image={IMAGE_MODEL}  ·  auth={mode}")
    server.serve_forever()


if __name__ == "__main__":
    main()

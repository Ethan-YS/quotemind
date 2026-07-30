"""LLM access layer — pluggable backends behind one call site.

Backend is chosen by QUOTEMIND_BACKEND, or auto-detected:

- "gemini"     : Google Gemini API (needs GEMINI_API_KEY).
- "claude-cli" : shells out to a locally authenticated Claude Code CLI
                 (`claude -p`, headless). No API key ever touches this
                 codebase — auth lives in the CLI.
- "demo"       : replays the bundled demo cache, so reviewers can run the
                 full flow with zero setup.

Auto-detection: GEMINI_API_KEY set -> gemini, else demo (QUOTEMIND_DEMO=1
forces demo). The demo cache itself is a snapshot of a real pipeline run
through a live backend — regenerate it with scripts/regen_demo_cache.py —
so replayed outputs are genuine model output, not hand-written fixtures.

The rest of the pipeline never knows which backend it is on. This is the
model-agnostic abstraction argued for in docs/solution-design.md §3.2,
demonstrated rather than asserted.
"""

import json
import mimetypes
import os
import re
import subprocess
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "demo_cache"
GEMINI_MODEL = os.getenv("QUOTEMIND_MODEL", "gemini-2.5-pro")


def backend() -> str:
    b = os.getenv("QUOTEMIND_BACKEND")
    if b:
        return b
    if os.getenv("QUOTEMIND_DEMO") == "1":
        return "demo"
    return "gemini" if os.getenv("GEMINI_API_KEY") else "demo"


def backend_label() -> str:
    return {"gemini": GEMINI_MODEL, "claude-cli": "claude-cli"}.get(backend(), "demo")


def call_llm(stage: str, prompt: str, image_path: str | None = None) -> dict:
    """Run one pipeline stage. Returns parsed JSON."""
    b = backend()
    if b == "gemini":
        return _gemini_json(prompt, image_path)
    if b == "claude-cli":
        return _claude_cli_json(prompt, image_path)
    cached = CACHE_DIR / f"{stage}.json"
    if not cached.exists():
        raise RuntimeError(
            f"Demo cache missing for stage '{stage}' and no live backend configured."
        )
    return json.loads(cached.read_text())


# --------------------------------------------------------------- backends --

def _gemini_json(prompt: str, image_path: str | None = None) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY from env
    contents: list = []
    if image_path:
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        contents.append(
            types.Part.from_bytes(data=Path(image_path).read_bytes(), mime_type=mime)
        )
    contents.append(prompt)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(resp.text)


def _claude_cli_json(prompt: str, image_path: str | None = None) -> dict:
    full = prompt + "\n\nReturn ONLY the JSON object — no markdown fences, no commentary."
    cmd = ["claude", "-p", "--output-format", "text"]
    if image_path:
        full = (
            "First, use the Read tool to view the engineering drawing image at:\n"
            f"{Path(image_path).resolve()}\n\n"
        ) + full
        cmd += ["--allowedTools", "Read"]
    result = subprocess.run(
        cmd, input=full, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude-cli failed: {result.stderr[:500]}")
    return _extract_json(result.stdout)


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction: strip fences, take outermost object."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(text[start : end + 1])

"""LLM access layer.

Two modes, selected automatically:

- live mode  : GEMINI_API_KEY is set -> real Gemini calls (JSON output).
- demo mode  : no key (or QUOTEMIND_DEMO=1) -> replay pre-computed pipeline
               outputs for the bundled GS-4032 sample, so reviewers can run
               the full flow with zero setup.

The rest of the pipeline never knows which mode it is in — this mirrors the
model-agnostic abstraction argued for in docs/solution-design.md.
"""

import json
import mimetypes
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "demo_cache"
MODEL = os.getenv("QUOTEMIND_MODEL", "gemini-2.5-pro")


def live_enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY")) and os.getenv("QUOTEMIND_DEMO") != "1"


def call_llm(stage: str, prompt: str, image_path: str | None = None) -> dict:
    """Run one pipeline stage. Returns parsed JSON."""
    if live_enabled():
        return _gemini_json(prompt, image_path)
    cached = CACHE_DIR / f"{stage}.json"
    if not cached.exists():
        raise RuntimeError(
            f"Demo cache missing for stage '{stage}' and no GEMINI_API_KEY set."
        )
    return json.loads(cached.read_text())


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
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(resp.text)

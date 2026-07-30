"""QuoteMind API — five pipeline stages, each behind a human-in-the-loop gate.

Each stage is a separate endpoint on purpose: the frontend passes the
*human-reviewed* (possibly edited) output of stage N into stage N+1, so the
edit-then-continue loop is enforced by the API shape itself, not by UI
goodwill. See docs/solution-design.md §3.4.
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline import bom_agent, drawing_agent, process_agent, quote_agent, retrieval
from pipeline.llm import backend, backend_label

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
DRAWING_PNG = SAMPLES / "GS-4032_RevB.png"
UPLOADS = Path(__file__).resolve().parent / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
UPLOAD_EXTS = {".png", ".jpg", ".jpeg"}
UPLOAD_MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="QuoteMind", version="0.1.0")


class DrawingIn(BaseModel):
    rfq_text: str
    upload_id: str | None = None  # id returned by /api/upload; None = bundled sample


class RetrieveIn(BaseModel):
    card: dict


class BomIn(BaseModel):
    card: dict
    matches: dict


class ProcessIn(BaseModel):
    card: dict
    bom: dict
    matches: dict


class QuoteIn(BaseModel):
    rfq_text: str
    card: dict
    bom: dict
    routing: dict
    matches: dict


@app.get("/api/status")
def status():
    b = backend()
    return {"mode": "demo" if b == "demo" else "live", "backend": b, "model": backend_label()}


@app.get("/api/sample")
def sample():
    return {
        "rfq_text": (SAMPLES / "rfq_email.txt").read_text(),
        "drawing_url": "/samples/GS-4032_RevB.png",
        "drawing_svg_url": "/samples/GS-4032_RevB.svg",
    }


@app.post("/api/upload")
async def upload(file: UploadFile):
    """Accept a customer drawing for live-mode analysis (demo mode replays the sample)."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in UPLOAD_EXTS:
        raise HTTPException(400, f"unsupported file type '{ext}' — use PNG or JPG")
    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(400, "file exceeds 10 MB limit")
    upload_id = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS / upload_id).write_bytes(data)
    return {"upload_id": upload_id, "url": f"/uploads/{upload_id}"}


def _resolve_drawing(upload_id: str | None) -> Path:
    if not upload_id:
        return DRAWING_PNG
    # basename-only lookup inside the uploads dir — no client-controlled paths
    path = UPLOADS / Path(upload_id).name
    if not path.is_file():
        raise HTTPException(404, "unknown upload_id")
    return path


@app.post("/api/stage/drawing")
def stage_drawing(body: DrawingIn):
    return drawing_agent.run(body.rfq_text, str(_resolve_drawing(body.upload_id)))


@app.post("/api/stage/retrieve")
def stage_retrieve(body: RetrieveIn):
    return retrieval.find_similar(body.card)


@app.post("/api/stage/bom")
def stage_bom(body: BomIn):
    return bom_agent.run(body.card, body.matches)


@app.post("/api/stage/process")
def stage_process(body: ProcessIn):
    return process_agent.run(body.card, body.bom, body.matches)


@app.post("/api/stage/quote")
def stage_quote(body: QuoteIn):
    return quote_agent.run(body.rfq_text, body.card, body.bom, body.routing, body.matches)


app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")

"""QuoteMind API — five pipeline stages, each behind a human-in-the-loop gate.

Each stage is a separate endpoint on purpose: the frontend passes the
*human-reviewed* (possibly edited) output of stage N into stage N+1, so the
edit-then-continue loop is enforced by the API shape itself, not by UI
goodwill. See docs/solution-design.md §3.4.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline import bom_agent, drawing_agent, process_agent, quote_agent, retrieval
from pipeline.llm import MODEL, live_enabled

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
DRAWING_PNG = SAMPLES / "GS-4032_RevB.png"

app = FastAPI(title="QuoteMind", version="0.1.0")


class DrawingIn(BaseModel):
    rfq_text: str


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
    return {"mode": "live" if live_enabled() else "demo", "model": MODEL}


@app.get("/api/sample")
def sample():
    return {
        "rfq_text": (SAMPLES / "rfq_email.txt").read_text(),
        "drawing_url": "/samples/GS-4032_RevB.png",
        "drawing_svg_url": "/samples/GS-4032_RevB.svg",
    }


@app.post("/api/stage/drawing")
def stage_drawing(body: DrawingIn):
    return drawing_agent.run(body.rfq_text, str(DRAWING_PNG))


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
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")

"""Regenerate the demo cache by running the REAL pipeline through a live backend.

    QUOTEMIND_BACKEND=claude-cli python scripts/regen_demo_cache.py

All four LLM stages are validated against the schema the frontend depends on
before anything is written — a failed run leaves the existing cache intact.
"""

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("QUOTEMIND_BACKEND", "claude-cli")

from pipeline import bom_agent, drawing_agent, process_agent, quote_agent, retrieval  # noqa: E402
from pipeline.llm import CACHE_DIR, backend  # noqa: E402

ROOT = BACKEND_DIR.parent
RFQ = (ROOT / "samples" / "rfq_email.txt").read_text()
PNG = str(ROOT / "samples" / "GS-4032_RevB.png")

COST_KEYS = {"material", "machining", "heat_treatment", "grinding", "overhead"}


def check(cond, msg):
    if not cond:
        raise SystemExit(f"VALIDATION FAILED: {msg} — cache NOT written")


def validate_drawing(c):
    for k in ("part_name", "drawing_no", "material", "part_type", "max_dia_mm",
              "length_mm", "quantities", "features", "critical_requirements",
              "field_confidence", "review_flags"):
        check(k in c, f"drawing missing '{k}'")
    check(c["features"] and all("feature" in f and "spec" in f and "manufacturing_implication" in f
          for f in c["features"]), "drawing features malformed")


def validate_bom(b):
    check(b.get("bom_lines"), "bom_lines empty")
    for l in b["bom_lines"]:
        for k in ("pos", "item", "spec", "qty", "unit", "est_unit_cost_eur", "basis"):
            check(k in l, f"bom line missing '{k}'")
    for k in ("spec", "stock_size", "gross_weight_kg", "net_weight_kg"):
        check(k in b.get("raw_material", {}), f"raw_material missing '{k}'")
    check("open_questions" in b, "bom missing open_questions")


def validate_process(r):
    check(r.get("routing"), "routing empty")
    for o in r["routing"]:
        for k in ("op", "operation", "workcenter", "setup_min", "cycle_min_per_pc",
                  "basis", "confidence"):
            check(k in o, f"routing op missing '{k}'")
        check(o["confidence"] in ("high", "medium", "low"), "bad confidence value")
    check("plant" in r.get("recommended_plant", {}) and "why" in r["recommended_plant"],
          "recommended_plant malformed")
    check("critical_ops_notes" in r and "open_questions" in r, "process notes missing")


def validate_quote(q):
    check(len(q.get("scenarios", [])) == 2, "expected 2 quantity scenarios")
    for s in q["scenarios"]:
        for k in ("qty", "unit_cost_eur", "cost_breakdown_eur", "unit_price_eur", "margin_pct"):
            check(k in s, f"scenario missing '{k}'")
        check(set(s["cost_breakdown_eur"]) == COST_KEYS,
              f"cost_breakdown keys {set(s['cost_breakdown_eur'])} != {COST_KEYS}")
    check("amount" in q.get("tooling_cost_eur", {}), "tooling_cost_eur malformed")
    check("first_batch_weeks" in q.get("lead_time", {}), "lead_time malformed")
    for k in ("assumptions", "risks", "quote_letter_draft"):
        check(k in q, f"quote missing '{k}'")


print(f"backend: {backend()}")

print("stage 1/4 drawing …", flush=True)
card = drawing_agent.run(RFQ, PNG)
validate_drawing(card)
print(f"  -> {card['drawing_no']} {card['material']} · {len(card['features'])} features")

matches = retrieval.find_similar(card)  # deterministic, not cached
print(f"  retrieval: top={matches['matches'][0]['part']['part_no']} "
      f"score={matches['matches'][0]['score']}")

print("stage 2/4 bom …", flush=True)
bom = bom_agent.run(card, matches)
validate_bom(bom)
print(f"  -> {len(bom['bom_lines'])} lines, raw {bom['raw_material']['stock_size']}")

print("stage 3/4 process …", flush=True)
routing = process_agent.run(card, bom, matches)
validate_process(routing)
print(f"  -> {len(routing['routing'])} ops, plant {routing['recommended_plant']['plant']}")

print("stage 4/4 quote …", flush=True)
quote = quote_agent.run(RFQ, card, bom, routing, matches)
validate_quote(quote)
for s in quote["scenarios"]:
    print(f"  -> qty {s['qty']}: cost €{s['unit_cost_eur']} price €{s['unit_price_eur']}")

for name, data in (("drawing", card), ("bom", bom), ("process", routing), ("quote", quote)):
    (CACHE_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(f"cache written to {CACHE_DIR}")

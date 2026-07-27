"""Stage 3 — BOM draft generation, grounded in retrieved reference parts."""

import json

from .llm import call_llm

PROMPT = """You are a manufacturing engineer at PrecisionMotion GmbH. Draft a
single-level manufacturing BOM for the part below. Ground every estimate in
the reference parts (their real BOM/cost history is provided) and cite which
reference you used per line. Do not copy from references whose
cost_transferable flag is false — use them for geometry only.

Part feature card (already human-reviewed):
{card}

Reference parts from our history (with similarity reasons):
{matches}

Return JSON:
{{
  "bom_lines": [ {{ "pos": int, "item": str, "spec": str, "qty": number,
                   "unit": str, "est_unit_cost_eur": number,
                   "basis": str }} ],       // which reference part / rule
  "raw_material": {{ "spec": str, "stock_size": str, "gross_weight_kg": number,
                    "net_weight_kg": number, "scrap_note": str }},
  "open_questions": [ str ]                 // for the reviewing engineer
}}"""


def run(card: dict, matches: dict) -> dict:
    return call_llm(
        "bom",
        PROMPT.format(
            card=json.dumps(card, ensure_ascii=False, indent=1),
            matches=json.dumps(matches["matches"], ensure_ascii=False, indent=1),
        ),
    )

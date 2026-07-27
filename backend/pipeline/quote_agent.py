"""Stage 5 — Cost roll-up and quotation letter draft."""

import json

from .llm import call_llm

PROMPT = """You are a quotation engineer at PrecisionMotion GmbH. Roll up the
cost and draft a quotation for the RFQ below. Compute both requested quantity
scenarios. Be explicit about every assumption; the reviewing engineer signs
off before anything reaches the customer.

RFQ e-mail:
---
{rfq_text}
---

Part feature card: {card}
BOM draft (human-reviewed): {bom}
Routing draft (human-reviewed): {routing}
Reference parts (cost history): {matches}

Use a machine+labor rate of 78 EUR/h (Germany) or 52 EUR/h (Poland) per the
recommended plant, 12% overhead on manufacturing cost, and a 22% target margin.

Return JSON:
{{
  "scenarios": [ {{ "qty": int, "unit_cost_eur": number,
                   "cost_breakdown_eur": {{ "material": number, "machining": number,
                     "heat_treatment": number, "grinding": number, "overhead": number }},
                   "unit_price_eur": number, "margin_pct": number }} ],
  "tooling_cost_eur": {{ "amount": number, "note": str }},
  "lead_time": {{ "first_batch_weeks": number, "note": str }},
  "assumptions": [ str ],
  "risks": [ str ],
  "quote_letter_draft": str      // short professional e-mail body, English
}}"""


def run(rfq_text: str, card: dict, bom: dict, routing: dict, matches: dict) -> dict:
    return call_llm(
        "quote",
        PROMPT.format(
            rfq_text=rfq_text,
            card=json.dumps(card, ensure_ascii=False, indent=1),
            bom=json.dumps(bom, ensure_ascii=False, indent=1),
            routing=json.dumps(routing, ensure_ascii=False, indent=1),
            matches=json.dumps(matches["matches"], ensure_ascii=False, indent=1),
        ),
    )

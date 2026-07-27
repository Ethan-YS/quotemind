"""Stage 1 — Drawing Intelligence.

Vision LLM reads the engineering drawing + RFQ text and produces a
structured "part feature card". Every field carries a confidence level so
the human-in-the-loop UI can route low-confidence fields to mandatory
review (see HITL design in docs/solution-design.md §3.4).
"""

from .llm import call_llm

PROMPT = """You are a manufacturing engineer at PrecisionMotion GmbH reviewing an
incoming RFQ. Read the attached engineering drawing and the RFQ e-mail below,
then extract a part feature card as JSON.

RFQ e-mail:
---
{rfq_text}
---

Return JSON with exactly this shape:
{{
  "part_name": str, "drawing_no": str, "revision": str,
  "customer": str, "quantities": [int, ...],
  "material": str, "general_tolerances": str,
  "part_type": str,          // e.g. "gear_shaft"
  "max_dia_mm": number, "length_mm": number,
  "features": [ {{ "feature": str, "spec": str, "manufacturing_implication": str }} ],
  "critical_requirements": [ str ],   // tolerance-critical / certification items
  "field_confidence": {{ "<field>": "high"|"medium"|"low" }},
  "review_flags": [ str ]    // anything ambiguous a human MUST check
}}

Rules: extract only what is actually on the drawing or in the e-mail; if a
value is unreadable, set it null and add a review flag. Never invent numbers."""


def run(rfq_text: str, drawing_path: str) -> dict:
    return call_llm("drawing", PROMPT.format(rfq_text=rfq_text), image_path=drawing_path)

"""Stage 4 — Process routing draft, calibrated against reference routings."""

import json

from .llm import call_llm

PROMPT = """You are a process planner at PrecisionMotion GmbH. Draft a process
routing for the part below. Calibrate setup and cycle times against the
reference parts' real routings and costs. Flag any operation where the
estimate is weakly grounded.

Part feature card (human-reviewed):
{card}

BOM draft (human-reviewed):
{bom}

Reference parts:
{matches}

Return JSON:
{{
  "routing": [ {{ "op": int, "operation": str, "workcenter": str,
                 "setup_min": number, "cycle_min_per_pc": number,
                 "basis": str, "confidence": "high"|"medium"|"low" }} ],
  "recommended_plant": {{ "plant": str, "why": str }},
  "critical_ops_notes": [ str ],    // e.g. grinding for h6 seats, hardening distortion
  "open_questions": [ str ]
}}"""


def run(card: dict, bom: dict, matches: dict) -> dict:
    return call_llm(
        "process",
        PROMPT.format(
            card=json.dumps(card, ensure_ascii=False, indent=1),
            bom=json.dumps(bom, ensure_ascii=False, indent=1),
            matches=json.dumps(matches["matches"], ensure_ascii=False, indent=1),
        ),
    )

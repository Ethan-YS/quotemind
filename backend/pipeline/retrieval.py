"""Stage 2 — Similar part retrieval.

Deliberately NOT an LLM call: engineering similarity is constraint
satisfaction plus proximity, so the prototype implements the *structured*
channel of the hybrid retrieval described in docs/solution-design.md §3.3
(dense/sparse channels are a production concern). Deterministic, explainable,
and it runs offline — every match returns the reasons it scored.
"""

import json
from pathlib import Path

PARTS_DB = Path(__file__).resolve().parent.parent / "data" / "parts_db.json"

# Material base grade -> rough cost class. Matching class means historical
# cost figures are transferable; a class jump means they are not.
MATERIAL_CLASS = {
    "42CrMo4": "alloy_steel", "C45E": "carbon_steel", "16MnCr5": "case_steel",
    "20MnCr5": "case_steel", "X5CrNi18-10": "stainless", "Ti6Al4V": "exotic",
    "EN-GJS-400-15": "cast_iron",
}


def _material_class(material: str | None) -> str | None:
    if not material:
        return None
    for grade, cls in MATERIAL_CLASS.items():
        if grade.lower() in material.lower():
            return cls
    return None


def _proximity(a, b, tolerance):
    """1.0 at equal, linearly down to 0.0 at +/- tolerance."""
    if a is None or b is None:
        return 0.0
    return max(0.0, 1.0 - abs(a - b) / tolerance)


def _score(card: dict, part: dict) -> tuple[float, list[str], bool]:
    f = part["features"]
    score, reasons = 0.0, []

    if card.get("part_type") == part["family"]:
        score += 25
        reasons.append(f"Same part family ({part['family']})")

    same_material = False
    card_cls = _material_class(card.get("material"))
    part_cls = _material_class(part.get("material"))
    if card_cls and card_cls == part_cls:
        same_material = True
        score += 20
        reasons.append(f"Same material class ({part['material']})")
    elif card_cls and part_cls and part_cls == "exotic":
        score -= 15
        reasons.append(f"⚠ Exotic material ({part['material']}) — geometry may match, cost does NOT transfer")

    d = _proximity(card.get("max_dia_mm"), f.get("max_dia_mm"), 25)
    if d > 0:
        score += 15 * d
        reasons.append(f"Max diameter {f['max_dia_mm']} mm vs {card.get('max_dia_mm')} mm")
    l = _proximity(card.get("length_mm"), f.get("length_mm"), 80)
    if l > 0:
        score += 10 * l
        reasons.append(f"Length {f['length_mm']} mm vs {card.get('length_mm')} mm")

    card_specs = " ".join(
        str(x.get("spec", "")) + str(x.get("feature", "")) for x in card.get("features", [])
    ).lower()
    if f.get("spline") and ("spline" in card_specs or "din 5480" in card_specs):
        score += 10
        reasons.append(f"Splined shaft ({f['spline']})")
    if f.get("keyway") and "keyway" in card_specs:
        score += 5
        reasons.append(f"Keyway ({f['keyway']})")
    if f.get("hardening") and ("harden" in card_specs or "hrc" in card_specs):
        if "induction" in (f.get("hardening") or "") and "induction" in card_specs:
            score += 10
            reasons.append("Same hardening route (induction)")
        else:
            score += 4
            reasons.append(f"Hardened part ({f['hardening']}) — different route, verify cost")
    if f.get("bearing_seats") and "h6" in card_specs and "h6" in (f.get("bearing_seats") or ""):
        score += 5
        reasons.append(f"Ground h6 bearing seats ({f['bearing_seats']})")

    cost_transferable = same_material and score >= 55
    return round(min(score, 100), 1), reasons, cost_transferable


def find_similar(card: dict, top_n: int = 5) -> dict:
    parts = json.loads(PARTS_DB.read_text())
    scored, twins = [], []
    for part in parts:
        score, reasons, transferable = _score(card, part)
        scored.append({
            "part": part, "score": score, "reasons": reasons,
            "cost_transferable": transferable,
        })
        # Geometry twin with non-transferable cost basis: surface it explicitly
        # instead of letting it rank — the classic estimation trap.
        f = part["features"]
        if (
            card.get("part_type") == part["family"]
            and _proximity(card.get("max_dia_mm"), f.get("max_dia_mm"), 25) > 0.8
            and _proximity(card.get("length_mm"), f.get("length_mm"), 80) > 0.8
            and _material_class(card.get("material")) != _material_class(part.get("material"))
        ):
            twins.append({
                "part_no": part["part_no"], "name": part["name"],
                "material": part["material"],
                "note": "Near-identical geometry, but different material class — "
                        "excluded from cost calibration, usable for routing shape only.",
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "matches": scored[:top_n],
        "geometry_twins_excluded": twins,
        "searched": len(parts),
    }

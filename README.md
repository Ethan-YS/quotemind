# QuoteMind — AI RFQ→Quotation Agent

> IndustrialMind.ai Solution Design Challenge · Option B prototype
> Scenario: PrecisionMotion GmbH (fictional customer) · Full solution design: [docs/solution-design.md](docs/solution-design.md)
> 中文版：[README.zh.md](README.zh.md)

An end-to-end AI quotation pipeline: **customer RFQ + engineering drawing → part feature card → comparable-part retrieval → BOM draft → routing draft → cost breakdown + quotation letter**. Every stage is a human-in-the-loop gate: the next stage only runs on what the engineer has reviewed — including their corrections.

## Quick start

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --port 8000
# open http://localhost:8000
```

**No API key or model configuration required.** Once the dependencies are installed and the server is running, with no backend configured the app enters **demo mode** and replays a pre-generated run of the bundled sample (the GS-4032 gear shaft RFQ), so a reviewer can walk the full flow with zero setup.

**Live backends (any one of three):**

| Backend | How to enable | Notes |
|---|---|---|
| Gemini API | `export GEMINI_API_KEY=...` | Defaults to `gemini-2.5-pro`; override with `QUOTEMIND_MODEL` |
| Claude CLI | `QUOTEMIND_BACKEND=claude-cli` | Shells out to a locally authenticated Claude Code (`claude -p`, headless) — **no API key ever touches this codebase** |
| Codex CLI | `QUOTEMIND_BACKEND=codex-cli` | Same idea via `codex exec` (with `-i` for drawing vision); model set by `QUOTEMIND_CODEX_MODEL` (default `gpt-5.5`) |

Regenerate the demo cache: `QUOTEMIND_BACKEND=codex-cli python scripts/regen_demo_cache.py` — all four stages are schema-validated before anything is written, and a failed run leaves the existing cache intact.

## Architecture decisions (and why)

1. **One endpoint per stage, rather than one call that runs the whole chain.** The frontend passes the *human-reviewed* (possibly edited) output of stage N into stage N+1, so human-in-the-loop is enforced by the shape of the API and not by UI goodwill. This is the precondition for a manufacturer trusting AI at all: the judgement stays with the engineer.

2. **Comparable-part retrieval deliberately does not use an LLM.** Engineering similarity is constraint satisfaction plus proximity, and structured feature matching is the channel of hybrid retrieval that most needs to be right first: deterministic, explainable (every match carries its reasons), and runnable offline. A production system layers dense/sparse semantic channels on top (see solution design §3.3).

3. **An explicit "geometry twin" exclusion list.** Retrieval surfaces parts that are geometrically near-identical but of a different material class (a titanium prototype shaft, for instance): usable as a routing reference, useless for cost. This is the classic estimating trap, and the system turns it into an explicit output instead of silently getting it right or silently getting it wrong.

4. **The engineer can overrule retrieval — the hardest edge of HITL.** The algorithm knows whether features match; it does not know that "that batch had a furnace problem" or "we quoted that one below cost to win the account". Those live only in people's heads. So every match can be excluded, **with a mandatory stated reason**; excluded references never reach cost calibration in OP 40, and the reason is archived with the quotation (the "Engineer decisions" panel on OP 50). This step is not about editing numbers — it is about **overruling the evidence base the AI reasoned from**. Retrieval is precisely where domain knowledge beats the algorithm.

5. **The feature card is rule-checked, not merely eyeballed.** Material grades must be self-consistent within the card: change the material field and forget the line in "critical requirements", and the system names the contradictory entry and **blocks release**. But it does not pretend to be sure — a legitimate difference (a mating part, a coating, a supplier note) can be released by the engineer confirming it is deliberate, and that confirmation joins the decision archive. The "rule validation" node in the architecture diagram has an implementation behind it.

6. **OP 40 lets the engineer change the plan, not just its numbers.** BOM lines and operations can be added or removed (strike what the AI over-specified, add what it missed; removed lines never reach costing), and totals recalculate as you edit, so the consequence of a change is visible immediately. **Low-confidence operations must be signed off individually before release** — solution design §3.4 states "low confidence → mandatory human intervention", and this is its implementation rather than its promise. Every addition, removal and sign-off enters the "Engineer decisions" archive on OP 50.

7. **OP 50 is a commercial decision, not a read-only summary.** Margin and unit price are **linked in both directions** (edit either and the other follows; unit cost is carried over from OP 40 and stays read-only) — a shop needs both cost-plus quoting and target-price-backwards quoting. Tooling, lead time, assumptions and risks are all editable and extendable. **A disagreement between the quotation letter and the cost sheet hard-blocks sign-off** and offers one-click sync: a quotation whose letter says €98.69 while the cost sheet says €90.56 must never leave the company.

8. **Every AI output carries its basis and its confidence.** Which historical part a BOM line was derived from, which line the cycle times were calibrated against, which fields need human confirmation — traceability ahead of fluency. Every engineer correction is recorded and counted (the approval bar shows "N values corrected" live) and flows into the next stage — the seed of a production system's "human corrections feed the evaluation set".

9. **A provider-agnostic model layer.** The pipeline does not know whether it is live or replaying; switching between Gemini, Claude and a self-hosted open model touches one file, `llm.py`. For German customers, "can be switched to an EU region or on-prem deployment" is a precondition for signing, so this abstraction is a first-class concern rather than a nicety.

10. **The demo cache is a snapshot of real model output**, generated by running the actual pipeline through the codex-cli backend (gpt-5.5) via `scripts/regen_demo_cache.py`, with all four stages schema-validated before they were written. Every cost figure is anchored to a reference part's recorded actuals (check the `basis` field line by line) — these are not decorative numbers.

## Sample input / output

- **Input**: [samples/rfq_email.txt](samples/rfq_email.txt) (a Nordwind enquiry, 250 pcs + 500 pcs/yr) and [samples/GS-4032_RevB.svg](samples/GS-4032_RevB.svg) (engineering drawing of a 42CrMo4 splined gear shaft)
- **Intermediate**: feature card (13 features + review flags) → Top-5 comparable parts (best match PM-SH-1998 at 99.4; the titanium geometry twin explicitly excluded) → a 9-line operation-level BOM → a 12-operation routing (the model added a "post-hardening straightening" operation on its own initiative and flagged it low-confidence — exactly what HITL exists to put in front of a human)
- **Output**: cost breakdown for both quantity scenarios plus a quotation letter draft (€98.69 / €97.38, 8-week lead time, no tooling charge — the W30×1.5 spline hob is already in-house)

## What's real vs what's replayed

| Component | Demo mode | Live mode (any backend) |
|---|---|---|
| Comparable-part retrieval + geometry-twin exclusion | ✅ Runs for real (deterministic code, never replayed) | ✅ Runs for real |
| The four LLM stages (drawing / BOM / routing / quotation) | Replays the cache (which is itself a snapshot of a real live run) | ✅ Real model calls |
| HITL data flow (reviewed JSON passed into the next stage) | ✅ Genuinely passed on, but a replayed answer does not recompute from it | ✅ Corrections genuinely change downstream results |
| Production models and systems | — | See solution design §3.2 (swappable models, EU region / on-prem) |

## Repository layout

```
backend/
  app.py                  # FastAPI — five stage endpoints + static files
  pipeline/
    llm.py                # model abstraction (gemini / claude-cli / codex-cli / demo cache)
    drawing_agent.py      # ① drawing understanding → feature card
    retrieval.py          # ② comparable-part retrieval (structured matching, no LLM)
    bom_agent.py          # ③ BOM draft
    process_agent.py      # ④ routing draft
    quote_agent.py        # ⑤ cost roll-up + quotation letter
  data/
    parts_db.json         # 13 historical parts with cost and routing actuals
    demo_cache/           # pipeline output replayed in demo mode
  scripts/regen_demo_cache.py  # run the real pipeline on a live backend, validate, then write the cache
frontend/                 # review workbench (English UI, switchable to Chinese)
samples/                  # sample RFQ + engineering drawing
docs/solution-design.md   # full Part 1–5 solution design
```

## Known boundaries (the prototype's honest list)

- Drawing understanding handles a single-view drawing only; multi-page PDFs, assembly drawings and scanned hand sketches are production engineering work
- In demo mode, editing a blue value genuinely travels into the next stage's request, but the replayed LLM answer does not recompute from it — **the interface says so explicitly on those three stages**. Retrieval is deterministic and always computes for real, so corrections show up immediately in scores and cost-transferability
- OP 10 supports uploading your own drawing (PNG/JPG) and editing the RFQ text directly; this requires a live backend, and demo mode locks to the bundled sample and states why
- An undo stack, a change-history panel and field-level schema validation are production work; the prototype only reverts invalid input on numeric fields
- The 13-part library is hand-built demonstration data; a production system syncs it from PLM/ERP and applies hybrid retrieval
- Cost rates and assumptions are hard-coded in the prompts; a production system reads them from ERP master data
- No authentication, no concurrency control — this is a challenge prototype, not a product

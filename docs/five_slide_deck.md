# Incoming Request Processing Workflow — Five-Slide Summary Deck

Paste this directly into Gamma AI ("Paste in text" import). Each `#` starts a new
slide; sub-bullets carry the speaker content. Image references point at files
already in this repo (`images/`) so Gamma can pull them in during generation.

---

# Slide 1 — Problem Understanding and Objective

**The problem**
- BPO / customer support teams receive a constant, mixed stream of inbound requests across multiple channels — email, web forms, bulk file uploads — that today all funnel through the same manual triage step before any actual work can start.
- Four request types dominate the volume: complaints, general enquiries, service requests, and urgent escalations. Each needs a *different* multi-step remediation path, but a human has to read every single one first just to know which path applies.
- Manual triage is slow, inconsistent between agents, and has no structured audit trail — when a request goes wrong, there's no record of what was decided and why.

**The objective**
- Build a working AI-powered prototype that automatically classifies each incoming request (type + urgency + confidence) and executes the correct branching remediation workflow for that type, end to end, with no human touch on the clear-cut cases.
- Required for the cases the AI is *not* clear-cut on: a confidence-based human-review path with an override mechanism, so uncertain classifications pause for a person instead of guessing.
- Deliver this as a real, running system in a 3-day window — not a slide-only concept — with a persistent audit trail, a dashboard, batch processing for bulk queues, and documentation a reviewer can actually run.

---

# Slide 2 — Solution Architecture and Design Flow

**Stack**
- **FastAPI** — the single outward-facing API (submit, batch, log, dashboard, override, health).
- **LangGraph** `StateGraph` — the default orchestrator wiring classification and remediation together as nodes.
- **Groq** (Llama 3.3 70B) as the default LLM, swappable to OpenAI or Anthropic via one environment variable, no code changes.
- **SQLite** — the audit trail (`requests_log`): every request's classification, branch, remediation steps, outputs, and status.
- **Two frontends, one backend** — a Streamlit ops console and a custom "Request Classifier" web UI, both talking to the same REST API.

**Design principle: orchestration-agnostic architecture**
- Classification (`classify.py`) and remediation (`remediation/*.py`) are plain Python functions with zero LangGraph or HTTP awareness.
- `graph.py` is the *only* file that wires them into a flow. Swapping LangGraph for n8n or Retool later — both explicitly suggested in the brief — means rewiring HTTP nodes at that file, never touching the business logic.

**Routing flow** *(insert diagram — see `images/` screenshots or the ASCII diagram in `README.md` under "Workflow Design Notes")*
1. Classify the request → `request_type`, `urgency`, `confidence`, `sub_topic`, `is_gibberish`.
2. If `is_gibberish` → **Clarify branch**: skip every remediation path, ask the customer to resend with more detail.
3. Else if `confidence < 0.6` → **Human Review branch**: pause auto-resolution, queue for a human override, regardless of predicted type.
4. Else → route by `request_type` into one of four dedicated branches: **Complaint**, **General Enquiry**, **Service Request**, **Escalation**.
5. Every branch — including Human Review and Clarify — ends by writing a full record to the SQLite audit trail.

---

# Slide 3 — Implementation Highlights

**Key technical decisions**
- **Provider abstraction** (`llm_provider.py`): one factory function returns the active chat model; `LLM_PROVIDER=openai` in `.env` is the entire migration from Groq.
- **Central config** (`config.py`): every tunable constant — confidence threshold, SLA hours, follow-up windows, department routing map, timeouts — lives in one `pydantic-settings` object. Nothing is hardcoded inline in a remediation module.
- **Structured-output classification**: a single LLM call returns a typed `ClassificationResult`, which drives every downstream routing decision — no second "which branch" call needed.

**Branching logic in practice**
- Confidence and urgency are deliberately *decoupled*: urgency alone never forces human review. `escalation`-type requests are critical by definition, so if urgency triggered review too, the dedicated Escalation branch would be unreachable — its own first step is already "flag for human review."
- Gibberish input is checked *before* the confidence check and takes priority over both — an unintelligible request skips classification-based routing entirely rather than landing in the review queue with a meaningless AI guess attached.

**Reliability engineering**
- `tenacity` retry (3 attempts, exponential backoff) around the classification call — Groq's structured-output occasionally returns malformed JSON; a transient generation issue, not a logic bug.
- A hard 30-second client timeout on every LLM call, so a stalled provider request fails fast instead of hanging a worker.
- Batch endpoint isolates failures per item — one bad classification in a batch of 20 doesn't abort the other 19.

**Screenshot to include:** `images/marcus_input.png` + `images/marcus_output.png` (Complaint branch — shows the AI's classification, confidence score, remediation steps, and drafted acknowledgement side by side) or `images/devon_ip.png` + `images/devon_op.png` (Escalation branch, showing the human-in-the-loop flag firing at 0.99 confidence).

**Code snippet to include** (routing priority, from `backend/app/graph.py`):
```python
def route_after_classify(state: WorkflowState) -> str:
    if state["classification"].is_gibberish:
        return "clarify"
    if state["needs_human_review"]:
        return "human_review"
    return state["classification"].request_type
```

---

# Slide 4 — Challenges and Learnings

**Challenge 1 — a routing bug that made a whole branch unreachable**
Early logic treated `critical` urgency as its own trigger for human review. Since `escalation` requests are *always* critical, this meant the dedicated Escalation branch could never actually run — every escalation silently fell into Human Review instead. Fixed by triggering review on classification confidence alone, and locked in with a regression test (`test_high_confidence_critical_escalation_does_not_force_human_review`).

**Challenge 2 — structured output isn't 100% reliable**
Groq's Llama tool-calling occasionally emitted malformed JSON for the classification schema — not a prompt problem, a generation reliability problem. Solved with retries rather than trying to prompt-engineer it away.

**Challenge 3 — a CSS bug that looked like a logic bug**
The custom web frontend showed all three intake forms (Email, Web Form, File Upload) stacked simultaneously instead of switching between them. Root cause: author CSS (`.channel-form { display: flex }`) silently beat the browser's own `[hidden] { display: none }` default, regardless of source order — a specificity issue, not a JavaScript bug. A reminder that "the logic looks right" isn't the same as "the cascade agrees with you."

**Challenge 4 — a health check that lied**
`/health` originally returned `{"status": "ok"}` unconditionally, regardless of whether the database or the LLM API key were actually reachable/configured. Replaced with real checks and correct `200`/`503` status codes — a good example of a bug that's invisible until the exact moment you need the health check to be honest.

**Trade-off made under the time-box**
SQLite is the right choice for a 3-day prototype's audit trail, but it's ephemeral on Render's free tier — wiped on every redeploy. Documented as a known limitation rather than solved, since a persistent disk or hosted Postgres was out of scope for the deadline.

**Biggest takeaway**
Keeping orchestration (LangGraph) fully decoupled from business logic (plain functions) meant every one of the fixes above was a localized, single-file change — never a cross-cutting rewrite. That architectural choice paid for itself repeatedly during the build.

---

# Slide 5 — Demo Summary and Next Steps

**What's built**
- A FastAPI + LangGraph backend classifying 4 request types plus 2 cross-cutting branches (Human Review, Clarify) across 3 intake channels (email, web form, file upload), backed by a SQLite audit trail, a dashboard, batch processing, and a human override endpoint.
- Two working frontends against the same backend, both deployed.

**Links**
- Repository: `https://github.com/n3utr7no/request-classifier`
- Live demo (Streamlit): `https://request-classifier-streamlit.onrender.com/`
- Sample inputs/outputs and full setup instructions: `README.md` in the repo root.

**Potential enhancements with more time**
- Replace `[SIMULATED]` routing/notification calls with real Slack webhook and SMTP integrations — each is already a single, isolated function call, so this is a localized change, not a redesign.
- Move the audit trail off SQLite's ephemeral free-tier disk to Postgres, for durability across redeploys.
- Add an n8n or Retool orchestration layer as an alternative to LangGraph, exercising the orchestration-agnostic architecture as designed.
- Let the Clarify branch loop back and re-classify once the customer resends clarified text, instead of ending the flow after a single ask.
- Add authentication and rate-limiting to the public API before any production use.
- Richer dashboard analytics: SLA-breach tracking, per-agent override rates, confidence-score trends over time.

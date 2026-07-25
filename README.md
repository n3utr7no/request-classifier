# Incoming Request Processing Workflow

An AI-powered prototype that classifies incoming customer requests (complaints, enquiries,
service requests, urgent escalations) and executes a distinct, multi-step remediation
workflow per type — with an audit trail, dashboard, batch processing, and a human
escalation-override mechanism for cases the AI is unsure about.

Two frontends ship against the same backend: a Streamlit console (`frontend/`) and a
standalone HTML/CSS/JS site called "Request Classifier" (`frontend-web/`, not part of the
deployment covered below).

## Live Link: https://request-classifier-streamlit.onrender.com/

## Setup Instructions

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # then set GROQ_API_KEY (or switch LLM_PROVIDER + the matching key)

uvicorn app.main:app --reload --port 8000
```

In a second terminal, the Streamlit console:

```bash
cd frontend
streamlit run streamlit_app.py
```

### Switching LLM provider

Edit `backend/.env`:

```
LLM_PROVIDER=openai        # or anthropic
OPENAI_API_KEY=sk-...
```

No code changes required — `backend/app/llm_provider.py` is the single factory every
module calls through.

### Running the tests

```bash
cd backend
pytest -v
```

28 tests: config defaults, Pydantic validation, SQLite CRUD/aggregation, all five
remediation branches (LLM calls mocked, so these run offline), the classify→route decision,
health-check behavior, and the FastAPI endpoints (submission, batch error isolation,
override, dashboard).

## Deployment (Render)

Render is used instead of Vercel: this app is two long-running Python processes
(FastAPI + Streamlit) with a stateful SQLite file behind them, and Streamlit needs a
persistent WebSocket connection — none of that fits Vercel's serverless model, which is
built for stateless functions and static sites. `frontend-web/` (the static site) is left
out of this deployment on purpose, per project scope.

A `render.yaml` blueprint at the repo root defines both services. Steps:

1. Push this repo to GitHub (see below).
2. In the Render dashboard: **New +** → **Blueprint** → connect this repository. Render
   reads `render.yaml` and proposes two services:
   - `request-classifier-backend` — FastAPI, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`,
     health-checked at `/health`
   - `request-classifier-streamlit` — Streamlit, pointed at the backend via `API_BASE`
3. Before the first deploy, set the secret env vars on the **backend** service (Render
   prompts for these since `render.yaml` marks them `sync: false`):
   - `GROQ_API_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, matching `LLM_PROVIDER`)
4. Deploy. Once the backend service is live, note its actual Render URL (something like
   `https://request-classifier-backend.onrender.com`) and confirm it matches the
   `API_BASE` value in `render.yaml` for the Streamlit service — if Render assigned a
   different subdomain, update that env var on the Streamlit service and redeploy it.
5. Open the Streamlit service's URL — it talks to the backend over the public `API_BASE`
   URL, exactly like it talks to `127.0.0.1:8000` locally.

**Known limitation:** Render's free-tier filesystem is ephemeral — `db/requests.db` (the
audit trail) is wiped on every redeploy or restart. Fine for a demo; a real deployment
would move to a persistent disk or a hosted database.

## Workflow Design Notes

```
                    ┌──────────────┐
   incoming request │  classify()  │  LLM structured-output call
   ─────────────────▶  (LLM call)  │  -> request_type, urgency, confidence, sub_topic, is_gibberish
                    └──────┬───────┘
                           │
                  is_gibberish ?
                 ┌─────────┴─────────┐
                yes                  no
                 │                    │
                 ▼           confidence < 0.6 ?
         ┌───────────────┐   ┌─────────┴─────────┐
         │   clarify     │  yes                  no
         │ (no intent to │   │                    │
         │  act on, ask  │   ▼                    ▼
         │  to rephrase) │  ┌───────────────┐   route by request_type
         └───────┬───────┘  │ human_review  │   ┌───────┬────────────┬─────────────────┬────────────┐
                 │          │ (AI unsure,   │   │       │            │                 │            │
                 │          │ pause & wait  │ complaint general_enquiry service_request  escalation
                 │          │ for override) │   │       │            │                 │            │
                 │          └───────┬───────┘   ▼       ▼            ▼                 ▼            │
                 │                  │      each branch runs ≥2 remediation steps, then logs to SQLite│
                 └──────────────────┴──────────────────────────────┬────────────────────────────────┘
                                                                    ▼
                                                        requests_log (audit trail)
```

Routing is decided in three steps, checked in this order. First, `raw_text` must be at
least 10 characters or the API rejects it outright (`422`) before classification ever
runs. Second, the LLM assigns a `request_type`, `urgency`, `confidence`, and an
`is_gibberish` flag; if `is_gibberish` is true (input has no discernible customer
intent — random characters, keyboard mashing) the request is routed straight to
**clarify**, which asks the customer to resend with more detail and skips every
remediation branch and the confidence check entirely. Third, if the input is intelligible
but confidence falls below a configurable threshold (default `0.6`), the request is
routed to **human_review** regardless of predicted type — this is the brief's "escalation
override for edge cases the AI is uncertain about." Otherwise it's routed by
`request_type` into one of four dedicated branches. Every branch, including
`human_review` and `clarify`, ends by writing a full record (classification, branch,
steps taken, generated outputs, status) to a SQLite audit trail.

A human reviewer can later call the override endpoint on any logged request (not just
ones the AI flagged) to supply a corrected classification; the case is re-run through the
correct branch and the log entry keeps both the original AI classification and the human
correction, so the audit trail always shows what the AI decided and what a human changed.

**Note on urgency vs. human review:** `escalation`-type requests are, by definition,
almost always `critical` urgency. If urgency alone triggered human review, the dedicated
escalation branch would never run. Human review is triggered only by low classification
confidence; urgent/critical requests are handled deterministically by the `escalation`
branch, whose first step is itself "flag for human review."

### Classification

One LLM call per request returns a structured `ClassificationResult`:

| Field | Description |
|---|---|
| `request_type` | `complaint` \| `general_enquiry` \| `service_request` \| `escalation` |
| `urgency` | `low` \| `medium` \| `high` \| `critical` |
| `confidence` | 0-1, how sure the model is about `request_type` |
| `sub_topic` | e.g. `billing`, `technical`, `account`, `general`; used for KB lookup / department routing |
| `reasoning` | one-sentence justification, kept in the audit trail |
| `is_gibberish` | true when the input text has no discernible customer intent (random characters, keyboard mashing); routes to the Clarify branch instead of any remediation branch |

`raw_text` also has a hard `min_length=10` at the API boundary (`RequestIn` model) — anything
shorter is rejected with `422` before it ever reaches classification.

### Intake channels

Three channels, each its own form on the Customer side:

| Channel | What it collects |
|---|---|
| Email | From address (doubles as customer identifier), Subject, Body |
| Web Form | Email, optional full name, Topic, Message |
| File Upload | A CSV (`customer_id, subject, body`), auto-processed in configurable batches (default 4) |

Email and Web Form identify the customer by email address. File Upload keeps an explicit
`customer_id` column since one file can carry requests for many different customers at once.

## Remediation Strategy Definitions

| Type | Urgency | Steps | Status after |
|---|---|---|---|
| **Complaint** | High | Acknowledge receipt (LLM draft) → Escalate to senior handler → Log with priority flag → Set 2h follow-up reminder | `escalated` |
| **General Enquiry** | Low | Classify sub-topic → Generate response from knowledge base (LLM + KB lookup) → Send response → Log resolved | `resolved` |
| **Service Request** | Medium | Extract required details (LLM) → Route to department (config-driven mapping) → Generate confirmation (LLM) → Set SLA timer (24h) | `in_progress` |
| **Escalation / Urgent** | Critical | Flag for human review → Draft urgent acknowledgement (LLM) → Notify supervisor → Pause auto-resolution | `pending_review` |
| **Human Review** (cross-cutting, low-confidence) | any | Flag low-confidence case → Draft generic acknowledgement (LLM) → Notify supervisor → Pause pending override | `pending_review` |
| **Clarify** (cross-cutting, unintelligible input) | any | Detect unintelligible input → skip classification-based routing entirely → return a request to rephrase | `needs_clarification` |

The Clarify branch takes priority over both the confidence-based Human Review branch and normal
type-based routing: if `is_gibberish` is true, the request is never handed to a department, drafted
a response, or queued for human review — there is no discernible intent to act on, so the only
output is a plain-language ask for the customer to resend with more detail.

Notifications/routing ("Escalated to Senior Handler Queue", "Routed to Billing Team", etc.)
are simulated: logged with a `[SIMULATED]` prefix rather than calling real Slack/email
APIs. Each is a single function call in `backend/app/remediation/*.py`, so wiring in a
real Slack webhook or SMTP call later is a localized change, not a redesign.

Every tunable constant (confidence threshold, SLA/follow-up durations, department
routing map, LLM provider/model names) lives in one place, `backend/app/config.py`,
overridable via `.env`. Nothing is hardcoded inline in a remediation module.

## Sample Input Requests and Corresponding Output Logs

One real request per branch type, submitted to the live backend and captured verbatim
(also saved as JSON at [`docs/sample_outputs.json`](docs/sample_outputs.json)).

### Complaint
**Input** (email from `jane.doe@example.com`):
> Subject: Charged twice this month
>
> I have been charged twice for my subscription this month and nobody has responded to my last two emails. This is completely unacceptable and I want a refund immediately.

**Output log:**
```json
{
  "classification_type": "complaint",
  "urgency": "high",
  "confidence": 0.9,
  "branch_taken": "complaint",
  "remediation_steps": [
    "Acknowledged receipt of complaint",
    "Escalated to senior handler",
    "Logged case with priority flag",
    "Set 2-hour follow-up reminder"
  ],
  "outputs": {
    "draft_acknowledgement": "Dear Jane, We apologize for the inconvenience you've experienced with being charged twice for your subscription this month. We acknowledge receipt of your complaint and want to assure you that we are actively looking into this matter...",
    "routing_notification": "[SIMULATED] Escalated to: Senior Handler Queue",
    "priority_flag": "high",
    "follow_up_due_at": "2026-07-25T17:04:46.665281+00:00"
  },
  "status": "escalated"
}
```

### General Enquiry
**Input** (web form, topic Billing, from `sam.oduya@example.com`):
> Can you tell me when my next invoice is due and how I can view previous invoices online?

**Output log:**
```json
{
  "classification_type": "general_enquiry",
  "urgency": "low",
  "confidence": 0.9,
  "branch_taken": "general_enquiry",
  "remediation_steps": [
    "Classified sub-topic: billing",
    "Generated AI response from knowledge base",
    "Sent response to customer",
    "Logged as resolved"
  ],
  "outputs": {
    "draft_response": "Your next invoice will be issued on the 1st of the upcoming month and will be due for payment within 14 days. To view your previous invoices, you can log in to your account portal and navigate to the 'Billing' tab...",
    "kb_source": "billing",
    "send_notification": "[SIMULATED] Response sent to customer"
  },
  "status": "resolved"
}
```

### Service Request
**Input** (file upload row, `customer_id: CUST-1010`):
> Please cancel my add-on data package effective next billing cycle and confirm once it is done.

**Output log:**
```json
{
  "classification_type": "service_request",
  "urgency": "low",
  "confidence": 0.9,
  "branch_taken": "service_request",
  "remediation_steps": [
    "Extracted required details",
    "Routed to relevant department: Account Management",
    "Generated confirmation to requester",
    "Set SLA timer (24h)"
  ],
  "outputs": {
    "extracted_details": "The customer is requesting that their add-on data package be cancelled as of the start of their next billing cycle.",
    "routing_notification": "[SIMULATED] Routed to: Account Management",
    "draft_confirmation": "We have received your request to cancel your add-on data package, effective next billing cycle. Your request has been routed to our Account Management team for processing...",
    "sla_due_at": "2026-07-26T15:04:48.458853+00:00"
  },
  "status": "in_progress"
}
```

### Escalation / Urgent
**Input** (web form, from `priya.k@example.com`):
> URGENT: there appears to be unauthorized access on my account, someone changed my password and I can no longer log in. Please help immediately, I think I have been hacked.

**Output log:**
```json
{
  "classification_type": "escalation",
  "urgency": "critical",
  "confidence": 0.9,
  "branch_taken": "escalation",
  "remediation_steps": [
    "Immediately flagged for human review",
    "Drafted urgent acknowledgement",
    "Notified supervisor",
    "Paused auto-resolution pending human sign-off"
  ],
  "outputs": {
    "human_in_the_loop_flag": true,
    "draft_acknowledgement": "We understand the urgency and concern regarding the unauthorized access to your account, and we apologize for the inconvenience this has caused. Your issue has been immediately escalated to a supervisor for priority attention...",
    "supervisor_alert": "[SIMULATED] Supervisor notified via priority channel"
  },
  "status": "pending_review"
}
```

## Optional Enhancements Implemented

- **Batch processing** — CSV file upload processed in configurable batches (default 4),
  with per-item error isolation so one failed classification doesn't abort the rest
- **Audit trail** — full SQLite log of every classification decision and remediation action
- **Summary dashboard** — request volumes by type/status and average confidence
- **Escalation override mechanism** — human-in-the-loop correction for low-confidence or
  urgent cases, with a dedicated "Escalated" view of every request ever routed through
  the Escalation branch

## Architecture Notes

- **Orchestration:** LangGraph (`backend/app/graph.py`) wires classification and
  remediation into a state graph, but `classify.py` and `remediation/*.py` are plain
  functions with no orchestration awareness — swapping in n8n/Retool later is a rewiring
  exercise, not a rebuild.
- **LLM provider:** Groq by default, swappable to OpenAI or Anthropic via one environment
  variable, through the single factory in `llm_provider.py`.
- **Reliability:** every LLM call has a timeout and bounded retry; a stalled provider
  call fails and retries instead of hanging the request.

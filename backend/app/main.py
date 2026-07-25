from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.config import settings
from app.graph import run_override, run_workflow
from app.models import ClassificationResult, OverrideIn, RequestIn


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Incoming Request Processing Workflow", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> JSONResponse:
    checks: dict = {}
    healthy = True

    try:
        with db.get_connection() as conn:
            conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        healthy = False

    provider = settings.llm_provider.lower()
    api_key = {
        "groq": settings.groq_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "azure_openai": settings.azure_openai_api_key,
    }.get(provider, "")
    checks["llm_provider"] = provider
    checks["llm_api_key_configured"] = bool(api_key)
    if not api_key:
        healthy = False

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "error", "checks": checks},
    )


@app.post("/requests")
def submit_request(request_in: RequestIn) -> dict:
    final_state = run_workflow(request_in.raw_text, request_in.channel, request_in.customer_id)
    return db.get_request(final_state["request_id"])


@app.post("/requests/batch")
def submit_batch(requests_in: list[RequestIn]) -> list[dict]:
    """Processes each request independently: one item failing (e.g. a transient
    LLM error surviving classify_request's retries) is reported inline rather
    than aborting the whole batch, so a single bad item can't sink 15 good ones.
    """
    results = []
    for request_in in requests_in:
        try:
            final_state = run_workflow(request_in.raw_text, request_in.channel, request_in.customer_id)
            results.append(db.get_request(final_state["request_id"]))
        except Exception as exc:
            results.append({"raw_text": request_in.raw_text, "error": str(exc)})
    return results


@app.get("/requests")
def list_requests(limit: int = 200) -> list[dict]:
    return db.list_requests(limit=limit)


@app.get("/requests/{request_id}")
def get_request(request_id: str) -> dict:
    record = db.get_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return record


@app.post("/requests/{request_id}/override")
def override_request(request_id: str, override: OverrideIn) -> dict:
    record = db.get_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")

    corrected = ClassificationResult(
        request_type=override.request_type,
        urgency=override.urgency,
        confidence=1.0,
        sub_topic=None,
        reasoning=override.note or "Human override",
    )
    steps, outputs, status, branch = run_override(request_id, record["raw_text"], corrected)

    original_classification = record.get("original_classification") or {
        "request_type": record["classification_type"],
        "urgency": record["urgency"],
        "confidence": record["confidence"],
    }

    db.update_request(
        request_id,
        classification_type=corrected.request_type,
        urgency=corrected.urgency,
        confidence=corrected.confidence,
        branch_taken=branch,
        remediation_steps=steps,
        outputs=outputs,
        status=status,
        overridden=True,
        original_classification=original_classification,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return db.get_request(request_id)


@app.get("/dashboard/stats")
def dashboard_stats() -> dict:
    return db.dashboard_stats()

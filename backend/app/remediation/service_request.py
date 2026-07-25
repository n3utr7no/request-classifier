from datetime import datetime, timedelta, timezone

from app.config import settings
from app.drafting import draft_message
from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """Service Request branch: extract details -> route to dept -> confirmation -> SLA timer."""
    steps: list[str] = []
    outputs: dict = {}

    detail_summary = draft_message(
        "In one sentence, summarize exactly what action the customer wants performed "
        "on their account/service (this is an internal note, not sent to the customer).",
        raw_text,
    )
    steps.append("Extracted required details")
    outputs["extracted_details"] = detail_summary

    sub_topic = (classification.sub_topic or "general").lower()
    department = settings.department_routing.get(sub_topic, settings.department_routing["general"])
    steps.append(f"Routed to relevant department: {department}")
    outputs["routing_notification"] = f"[SIMULATED] Routed to: {department}"

    confirmation = draft_message(
        f"Confirm to the customer that their request has been received and routed to {department}, "
        f"with an expected response within {settings.service_request_sla_hours} hours.",
        raw_text,
    )
    steps.append("Generated confirmation to requester")
    outputs["draft_confirmation"] = confirmation

    sla_due_at = datetime.now(timezone.utc) + timedelta(hours=settings.service_request_sla_hours)
    steps.append(f"Set SLA timer ({settings.service_request_sla_hours}h)")
    outputs["sla_due_at"] = sla_due_at.isoformat()

    return steps, outputs, "in_progress"

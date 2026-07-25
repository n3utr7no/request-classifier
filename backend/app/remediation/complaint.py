from datetime import datetime, timedelta, timezone

from app.config import settings
from app.drafting import draft_message
from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """Complaint branch: acknowledge -> escalate to senior handler -> priority log -> follow-up."""
    steps: list[str] = []
    outputs: dict = {}

    acknowledgement = draft_message(
        "Acknowledge receipt of this complaint and reassure the customer it is being handled.",
        raw_text,
    )
    steps.append("Acknowledged receipt of complaint")
    outputs["draft_acknowledgement"] = acknowledgement

    steps.append("Escalated to senior handler")
    outputs["routing_notification"] = "[SIMULATED] Escalated to: Senior Handler Queue"

    steps.append("Logged case with priority flag")
    outputs["priority_flag"] = "high"

    follow_up_at = datetime.now(timezone.utc) + timedelta(hours=settings.complaint_followup_hours)
    steps.append(f"Set {settings.complaint_followup_hours}-hour follow-up reminder")
    outputs["follow_up_due_at"] = follow_up_at.isoformat()

    return steps, outputs, "escalated"

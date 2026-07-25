from app.drafting import draft_message
from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """Escalation/Urgent branch: flag for review -> urgent ack -> notify supervisor -> pause."""
    steps: list[str] = []
    outputs: dict = {}

    steps.append("Immediately flagged for human review")
    outputs["human_in_the_loop_flag"] = True

    acknowledgement = draft_message(
        "Draft an urgent acknowledgement letting the customer know this has been "
        "escalated to a supervisor and will be addressed as a priority.",
        raw_text,
    )
    steps.append("Drafted urgent acknowledgement")
    outputs["draft_acknowledgement"] = acknowledgement

    steps.append("Notified supervisor")
    outputs["supervisor_alert"] = "[SIMULATED] Supervisor notified via priority channel"

    steps.append("Paused auto-resolution pending human sign-off")

    return steps, outputs, "pending_review"

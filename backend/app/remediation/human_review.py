from app.drafting import draft_message
from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """Cross-cutting low-confidence branch: the brief's 'escalation override for edge
    cases the AI is uncertain about'. Triggered when classification confidence falls
    below the configured threshold, regardless of predicted request_type.

    Auto-remediation is paused here; a human calls POST /requests/{id}/override to
    supply the corrected classification and let the correct branch complete.
    """
    steps: list[str] = []
    outputs: dict = {}

    steps.append(
        f"Low-confidence classification ({classification.confidence:.2f}) flagged for human review"
    )
    outputs["ai_suggested_type"] = classification.request_type
    outputs["ai_suggested_urgency"] = classification.urgency
    outputs["ai_reasoning"] = classification.reasoning

    acknowledgement = draft_message(
        "Draft a brief, generic acknowledgement letting the customer know their request "
        "has been received and is being reviewed by a team member.",
        raw_text,
    )
    steps.append("Drafted generic acknowledgement")
    outputs["draft_acknowledgement"] = acknowledgement

    steps.append("Notified supervisor of low-confidence case")
    outputs["supervisor_alert"] = "[SIMULATED] Review queue notification sent"

    steps.append("Paused auto-resolution pending human override")

    return steps, outputs, "pending_review"

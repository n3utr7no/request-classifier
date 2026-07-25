from app.drafting import draft_message
from app.knowledge_base import lookup
from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """General Enquiry branch: classify sub-topic -> KB response -> send -> resolve."""
    steps: list[str] = []
    outputs: dict = {}

    sub_topic = classification.sub_topic or "general"
    steps.append(f"Classified sub-topic: {sub_topic}")

    kb_snippet = lookup(sub_topic)
    response = draft_message(
        f"Answer the customer's enquiry using this knowledge-base information: {kb_snippet}",
        raw_text,
    )
    steps.append("Generated AI response from knowledge base")
    outputs["draft_response"] = response
    outputs["kb_source"] = sub_topic

    steps.append("Sent response to customer")
    outputs["send_notification"] = "[SIMULATED] Response sent to customer"

    steps.append("Logged as resolved")

    return steps, outputs, "resolved"

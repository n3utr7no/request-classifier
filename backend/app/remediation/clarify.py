from app.models import ClassificationResult


def run(raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str]:
    """Cross-cutting branch for unintelligible input: triggered when classify_request
    sets is_gibberish=True. No remediation branch runs and no department/handler is
    notified — the request text carries no discernible intent to act on. The only
    output is a request back to the customer to rephrase.
    """
    steps = ["Detected unintelligible input", "Skipped classification-based routing"]
    outputs = {
        "clarification_request": (
            "We could not understand your request. Could you please resend it with more "
            "detail, for example what happened and what you would like us to do?"
        )
    }
    return steps, outputs, "needs_clarification"

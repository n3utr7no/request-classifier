"""Small mock knowledge base for the General Enquiry remediation branch.

In a real system this would be a vector-store lookup or a CRM's help-center
search. For this POC it's a static dict keyed by sub_topic, which is enough
to demonstrate "generate AI response from knowledge base" per the brief.
"""

KNOWLEDGE_BASE: dict[str, str] = {
    "billing": (
        "Invoices are issued on the 1st of each month and are due within 14 days. "
        "You can view and download past invoices from the 'Billing' tab in your account portal."
    ),
    "technical": (
        "Most connectivity issues are resolved by restarting your device and router. "
        "If the issue persists after 10 minutes, our Technical Support team can run a remote diagnostic."
    ),
    "account": (
        "You can update your contact details, plan, or payment method at any time from "
        "'Account Settings'. Changes to your plan take effect at the next billing cycle."
    ),
    "general": (
        "Our support hours are Monday-Friday, 8am-8pm, and Saturday 9am-2pm. "
        "You can reach us by phone, email, or live chat from our website."
    ),
}

DEFAULT_KB_ENTRY = (
    "We couldn't find a specific article for this topic. A member of our team will "
    "follow up with more detailed information shortly."
)


def lookup(sub_topic: str | None) -> str:
    if not sub_topic:
        return DEFAULT_KB_ENTRY
    return KNOWLEDGE_BASE.get(sub_topic.lower(), DEFAULT_KB_ENTRY)

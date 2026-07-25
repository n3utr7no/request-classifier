from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential

from app.llm_provider import get_chat_model
from app.models import ClassificationResult

CLASSIFY_SYSTEM_PROMPT = """\
You are a triage assistant for a general BPO / customer support operations team.
Classify the incoming customer request into exactly one request_type and one urgency level.

request_type must be one of:
- complaint: the customer is unhappy about something that already happened (billing error, \
poor service, broken product, rude staff, etc.)
- general_enquiry: the customer is asking a question or wants information, with no complaint \
or account-changing action implied
- service_request: the customer wants something done to their account/service (change plan, \
update details, request a callback, cancel/add a service, etc.)
- escalation: the request is urgent, high-stakes, or the customer is explicitly threatening to \
leave / involve legal / demanding a manager, or describes a safety/critical issue

urgency must be one of: low, medium, high, critical.

Also give a confidence score between 0 and 1 for how sure you are about request_type. Use a \
lower confidence when the request could plausibly belong to more than one category, or the \
text is ambiguous/incomplete.

If relevant, extract a short sub_topic (e.g. "billing", "technical", "account", "general").
Give a one-sentence reasoning for your classification.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def classify_request(raw_text: str, channel: str = "email") -> ClassificationResult:
    """Plain function: no HTTP/orchestration awareness.

    Called directly by graph.py's classify_node today; could equally be called
    from an n8n/Retool HTTP node wrapper later without any change here.

    Retries a few times because some providers (Groq's Llama tool-calling in
    particular) occasionally emit malformed structured-output JSON — a transient
    generation issue, not a logic bug, so a retry resolves it almost always.
    """
    llm = get_chat_model().with_structured_output(ClassificationResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CLASSIFY_SYSTEM_PROMPT),
            ("human", "Channel: {channel}\n\nRequest text:\n{raw_text}"),
        ]
    )
    chain = prompt | llm
    result = chain.invoke({"channel": channel, "raw_text": raw_text})
    return result

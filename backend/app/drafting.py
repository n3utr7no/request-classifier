"""Shared LLM text-drafting helper, reused by every remediation module.

Kept in one place so prompt plumbing (system framing, provider call) isn't
duplicated per-branch — each remediation module only supplies the specific
instruction and context for the message it needs drafted.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from app.llm_provider import get_chat_model

DRAFTING_SYSTEM_PROMPT = (
    "You are drafting a short, professional customer-support message on behalf of "
    "an operations team. Be concise (2-4 sentences), empathetic, and specific to the "
    "customer's request. Do not invent account details you were not given."
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def draft_message(instruction: str, raw_text: str) -> str:
    llm = get_chat_model()
    messages = [
        SystemMessage(content=DRAFTING_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Instruction: {instruction}\n\nOriginal customer request:\n{raw_text}"
        ),
    ]
    response = llm.invoke(messages)
    return response.content

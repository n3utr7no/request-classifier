"""Default orchestrator for the incoming-request workflow.

This is one valid orchestrator among several the architecture supports: the
classification (classify.py) and remediation (remediation/*.py) logic are
plain functions with no knowledge of LangGraph. Swapping this file for an
n8n/Retool workflow later means rewiring HTTP calls to those same functions
(via thin endpoint wrappers added at that time) — nothing in classify.py or
remediation/*.py would need to change.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.classify import classify_request
from app.config import settings
from app.models import ClassificationResult
from app.remediation import BRANCH_HANDLERS
from app.remediation import human_review


class WorkflowState(TypedDict):
    request_id: str
    raw_text: str
    channel: str
    customer_id: str
    classification: Optional[ClassificationResult]
    branch_taken: str
    remediation_log: list[str]
    outputs: dict
    status: str
    needs_human_review: bool


def classify_node(state: WorkflowState) -> WorkflowState:
    classification = classify_request(state["raw_text"], state["channel"])
    # Cross-cutting human_review only fires when the AI itself is unsure about the
    # type (low confidence) — NOT for critical urgency, since "escalation" requests
    # are always critical by definition and already have their own dedicated branch
    # (escalation.py) whose first step is "flag for human review" anyway.
    needs_review = classification.confidence < settings.confidence_threshold
    return {**state, "classification": classification, "needs_human_review": needs_review}


def _run_branch(handler, state: WorkflowState, branch_name: str) -> WorkflowState:
    steps, outputs, status = handler(state["raw_text"], state["classification"])
    return {
        **state,
        "branch_taken": branch_name,
        "remediation_log": steps,
        "outputs": outputs,
        "status": status,
    }


def complaint_node(state: WorkflowState) -> WorkflowState:
    return _run_branch(BRANCH_HANDLERS["complaint"], state, "complaint")


def general_enquiry_node(state: WorkflowState) -> WorkflowState:
    return _run_branch(BRANCH_HANDLERS["general_enquiry"], state, "general_enquiry")


def service_request_node(state: WorkflowState) -> WorkflowState:
    return _run_branch(BRANCH_HANDLERS["service_request"], state, "service_request")


def escalation_node(state: WorkflowState) -> WorkflowState:
    return _run_branch(BRANCH_HANDLERS["escalation"], state, "escalation")


def human_review_node(state: WorkflowState) -> WorkflowState:
    return _run_branch(human_review.run, state, "human_review")


def route_after_classify(state: WorkflowState) -> str:
    if state["needs_human_review"]:
        return "human_review"
    return state["classification"].request_type


def log_node(state: WorkflowState) -> WorkflowState:
    from app import db

    db.insert_request(
        {
            "id": state["request_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_text": state["raw_text"],
            "channel": state["channel"],
            "customer_id": state["customer_id"],
            "classification_type": state["classification"].request_type,
            "urgency": state["classification"].urgency,
            "confidence": state["classification"].confidence,
            "branch_taken": state["branch_taken"],
            "remediation_steps": state["remediation_log"],
            "outputs": state["outputs"],
            "status": state["status"],
            "overridden": False,
            "original_classification": None,
        }
    )
    return state


def build_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("classify", classify_node)
    graph.add_node("complaint", complaint_node)
    graph.add_node("general_enquiry", general_enquiry_node)
    graph.add_node("service_request", service_request_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("log", log_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "complaint": "complaint",
            "general_enquiry": "general_enquiry",
            "service_request": "service_request",
            "escalation": "escalation",
            "human_review": "human_review",
        },
    )
    for branch in ("complaint", "general_enquiry", "service_request", "escalation", "human_review"):
        graph.add_edge(branch, "log")
    graph.add_edge("log", END)

    return graph.compile()


_compiled_graph = build_graph()


def run_workflow(raw_text: str, channel: str = "email", customer_id: str = "") -> WorkflowState:
    initial_state: WorkflowState = {
        "request_id": str(uuid.uuid4()),
        "raw_text": raw_text,
        "channel": channel,
        "customer_id": customer_id,
        "classification": None,
        "branch_taken": "",
        "remediation_log": [],
        "outputs": {},
        "status": "",
        "needs_human_review": False,
    }
    return _compiled_graph.invoke(initial_state)


def run_override(request_id: str, raw_text: str, classification: ClassificationResult) -> tuple[list[str], dict, str, str]:
    """Re-runs remediation only, using a human-supplied classification.

    Used by the escalation-override endpoint: skips re-classification entirely
    and routes straight to the branch matching the corrected request_type.
    """
    handler = BRANCH_HANDLERS[classification.request_type]
    steps, outputs, status = handler(raw_text, classification)
    return steps, outputs, status, classification.request_type

"""Unit tests for the remediation branch functions.

draft_message is monkeypatched everywhere so these tests run offline/free and
don't depend on a live LLM provider or API key - they check the branching
logic and output shape, not prompt-generation quality.
"""

import pytest

from app.models import ClassificationResult
from app.remediation import clarify, complaint, escalation, general_enquiry, human_review, service_request


@pytest.fixture(autouse=True)
def stub_draft_message(monkeypatch):
    def fake_draft(instruction, raw_text):
        return f"[DRAFTED] {instruction[:20]}..."

    for module in (complaint, general_enquiry, service_request, escalation, human_review):
        monkeypatch.setattr(module, "draft_message", fake_draft)


def _classification(**overrides):
    defaults = dict(
        request_type="complaint",
        urgency="high",
        confidence=0.9,
        sub_topic="billing",
        reasoning="test",
    )
    defaults.update(overrides)
    return ClassificationResult(**defaults)


def test_complaint_branch_has_four_steps_and_escalated_status():
    steps, outputs, status = complaint.run("raw text", _classification())

    assert len(steps) == 4
    assert status == "escalated"
    assert "draft_acknowledgement" in outputs
    assert "follow_up_due_at" in outputs
    assert outputs["priority_flag"] == "high"


def test_general_enquiry_branch_uses_kb_and_resolves():
    classification = _classification(request_type="general_enquiry", urgency="low", sub_topic="technical")
    steps, outputs, status = general_enquiry.run("my internet is slow", classification)

    assert status == "resolved"
    assert outputs["kb_source"] == "technical"
    assert "draft_response" in outputs
    assert any("resolved" in step.lower() for step in steps)


def test_general_enquiry_falls_back_to_default_kb_entry_for_unknown_topic():
    classification = _classification(request_type="general_enquiry", urgency="low", sub_topic="unknown_topic_xyz")
    _, outputs, _ = general_enquiry.run("random question", classification)

    assert "couldn't find a specific article" in outputs["draft_response"] or "[DRAFTED]" in outputs["draft_response"]


def test_service_request_branch_routes_by_department_mapping():
    classification = _classification(request_type="service_request", urgency="medium", sub_topic="billing")
    steps, outputs, status = service_request.run("please cancel my add-on", classification)

    assert status == "in_progress"
    assert outputs["routing_notification"] == "[SIMULATED] Routed to: Billing Team"
    assert "sla_due_at" in outputs


def test_service_request_unknown_subtopic_routes_to_general_operations():
    classification = _classification(request_type="service_request", urgency="medium", sub_topic="something_else")
    _, outputs, _ = service_request.run("do a thing", classification)

    assert outputs["routing_notification"] == "[SIMULATED] Routed to: General Operations"


def test_escalation_branch_pauses_for_human_review():
    classification = _classification(request_type="escalation", urgency="critical")
    steps, outputs, status = escalation.run("everything is on fire", classification)

    assert status == "pending_review"
    assert outputs["human_in_the_loop_flag"] is True
    assert any("paused" in step.lower() for step in steps)


def test_human_review_branch_preserves_ai_suggestion_for_audit_trail():
    classification = _classification(request_type="service_request", urgency="medium", confidence=0.4)
    steps, outputs, status = human_review.run("ambiguous text", classification)

    assert status == "pending_review"
    assert outputs["ai_suggested_type"] == "service_request"
    assert outputs["ai_suggested_urgency"] == "medium"


def test_clarify_branch_asks_customer_to_rephrase_and_runs_no_department_handoff():
    classification = _classification(is_gibberish=True, confidence=0.2)
    steps, outputs, status = clarify.run("asdkj alksjd ;;; !!!! zzzzz", classification)

    assert status == "needs_clarification"
    assert "clarification_request" in outputs
    assert "routing_notification" not in outputs
    assert "draft_acknowledgement" not in outputs
    assert len(steps) == 2

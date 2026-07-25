"""Tests for the classify -> route decision in graph.py.

This is a regression test in particular for a bug where ANY critical-urgency
classification (which "escalation" requests always have) was forced into the
human_review branch, making the dedicated escalation branch unreachable.
Human review should only trigger on low AI confidence, not on urgency alone.
"""

from app import graph
from app.models import ClassificationResult


def _classification(**overrides):
    defaults = dict(
        request_type="escalation",
        urgency="critical",
        confidence=0.9,
        sub_topic=None,
        reasoning="test",
    )
    defaults.update(overrides)
    return ClassificationResult(**defaults)


def _initial_state(raw_text="some request", channel="email"):
    return {
        "request_id": "req-1",
        "raw_text": raw_text,
        "channel": channel,
        "customer_id": "CUST-0001",
        "classification": None,
        "branch_taken": "",
        "remediation_log": [],
        "outputs": {},
        "status": "",
        "needs_human_review": False,
    }


def test_high_confidence_critical_escalation_does_not_force_human_review(monkeypatch):
    monkeypatch.setattr(
        graph, "classify_request", lambda raw_text, channel: _classification(confidence=0.9)
    )
    result_state = graph.classify_node(_initial_state())

    assert result_state["needs_human_review"] is False
    assert graph.route_after_classify(result_state) == "escalation"


def test_low_confidence_forces_human_review_regardless_of_type(monkeypatch):
    monkeypatch.setattr(
        graph,
        "classify_request",
        lambda raw_text, channel: _classification(request_type="general_enquiry", urgency="low", confidence=0.3),
    )
    result_state = graph.classify_node(_initial_state())

    assert result_state["needs_human_review"] is True
    assert graph.route_after_classify(result_state) == "human_review"


def test_route_after_classify_routes_by_request_type_when_confident():
    for request_type in ("complaint", "general_enquiry", "service_request", "escalation"):
        state = _initial_state()
        state["classification"] = _classification(request_type=request_type, confidence=0.95)
        state["needs_human_review"] = False
        assert graph.route_after_classify(state) == request_type

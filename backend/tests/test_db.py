from app import db


def _sample_record(request_id="req-1", **overrides):
    record = {
        "id": request_id,
        "raw_text": "My internet has been down for two days.",
        "channel": "email",
        "customer_id": "CUST-1001",
        "classification_type": "complaint",
        "urgency": "high",
        "confidence": 0.92,
        "branch_taken": "complaint",
        "remediation_steps": ["Acknowledged receipt of complaint", "Escalated to senior handler"],
        "outputs": {"draft_acknowledgement": "We're sorry to hear that..."},
        "status": "escalated",
    }
    record.update(overrides)
    return record


def test_insert_and_get_round_trip():
    db.insert_request(_sample_record())
    fetched = db.get_request("req-1")

    assert fetched is not None
    assert fetched["customer_id"] == "CUST-1001"
    assert fetched["classification_type"] == "complaint"
    assert fetched["remediation_steps"] == [
        "Acknowledged receipt of complaint",
        "Escalated to senior handler",
    ]
    assert fetched["outputs"] == {"draft_acknowledgement": "We're sorry to hear that..."}
    assert fetched["overridden"] is False
    assert fetched["original_classification"] is None


def test_get_missing_request_returns_none():
    assert db.get_request("does-not-exist") is None


def test_update_request_applies_override_fields():
    db.insert_request(_sample_record())
    db.update_request(
        "req-1",
        classification_type="general_enquiry",
        status="resolved",
        overridden=True,
        original_classification={"request_type": "complaint", "urgency": "high", "confidence": 0.92},
    )
    fetched = db.get_request("req-1")

    assert fetched["classification_type"] == "general_enquiry"
    assert fetched["status"] == "resolved"
    assert fetched["overridden"] is True
    assert fetched["original_classification"] == {
        "request_type": "complaint",
        "urgency": "high",
        "confidence": 0.92,
    }


def test_list_requests_orders_most_recent_first():
    db.insert_request(_sample_record(request_id="req-1", timestamp="2026-01-01T00:00:00+00:00"))
    db.insert_request(_sample_record(request_id="req-2", timestamp="2026-01-02T00:00:00+00:00"))

    records = db.list_requests()

    assert [r["id"] for r in records] == ["req-2", "req-1"]


def test_dashboard_stats_aggregates_by_type_and_status():
    db.insert_request(_sample_record(request_id="req-1", classification_type="complaint", status="escalated"))
    db.insert_request(_sample_record(request_id="req-2", classification_type="complaint", status="escalated"))
    db.insert_request(_sample_record(request_id="req-3", classification_type="general_enquiry", status="resolved"))

    stats = db.dashboard_stats()

    assert stats["total_requests"] == 3
    assert stats["by_type"] == {"complaint": 2, "general_enquiry": 1}
    assert stats["by_status"] == {"escalated": 2, "resolved": 1}
    assert 0.0 < stats["avg_confidence"] <= 1.0

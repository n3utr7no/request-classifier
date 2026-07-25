"""API-level tests. run_workflow / run_override are monkeypatched on app.main
so these exercise routing, persistence, and error handling without ever
calling a live LLM provider.
"""

import pytest
from fastapi.testclient import TestClient

from app import db, main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_reports_ok_when_db_and_api_key_are_fine(client, monkeypatch):
    monkeypatch.setattr(main.settings, "groq_api_key", "fake-key-for-test")
    monkeypatch.setattr(main.settings, "llm_provider", "groq")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["llm_api_key_configured"] is True


def test_health_reports_error_when_api_key_missing(client, monkeypatch):
    monkeypatch.setattr(main.settings, "groq_api_key", "")
    monkeypatch.setattr(main.settings, "llm_provider", "groq")

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"]["llm_api_key_configured"] is False


def _fake_final_state(
    request_id, raw_text, channel="email", customer_id="CUST-0001", request_type="complaint", status="escalated"
):
    db.insert_request(
        {
            "id": request_id,
            "raw_text": raw_text,
            "channel": channel,
            "customer_id": customer_id,
            "classification_type": request_type,
            "urgency": "high",
            "confidence": 0.9,
            "branch_taken": request_type,
            "remediation_steps": ["step one", "step two"],
            "outputs": {"draft_acknowledgement": "..."},
            "status": status,
        }
    )
    return {"request_id": request_id}


def test_submit_request_returns_persisted_record(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "run_workflow",
        lambda raw_text, channel, customer_id: _fake_final_state("req-single", raw_text, channel, customer_id),
    )

    response = client.post(
        "/requests", json={"raw_text": "my bill is wrong", "channel": "email", "customer_id": "CUST-1234"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "req-single"
    assert body["customer_id"] == "CUST-1234"
    assert body["classification_type"] == "complaint"


def test_get_missing_request_returns_404(client):
    response = client.get("/requests/does-not-exist")
    assert response.status_code == 404


def test_batch_isolates_a_single_item_failure(client, monkeypatch):
    call_count = {"n": 0}

    def fake_run_workflow(raw_text, channel, customer_id):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated transient LLM failure")
        return _fake_final_state(f"req-{call_count['n']}", raw_text, channel, customer_id)

    monkeypatch.setattr(main, "run_workflow", fake_run_workflow)

    response = client.post(
        "/requests/batch",
        json=[
            {"raw_text": "request one", "channel": "email", "customer_id": "CUST-1"},
            {"raw_text": "request two - will fail", "channel": "email", "customer_id": "CUST-2"},
            {"raw_text": "request three", "channel": "email", "customer_id": "CUST-3"},
        ],
    )

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 3
    assert "error" in results[1]
    assert results[1]["error"] == "simulated transient LLM failure"
    assert "error" not in results[0]
    assert "error" not in results[2]


def test_override_preserves_original_classification_and_updates_status(client, monkeypatch):
    db.insert_request(
        {
            "id": "req-override",
            "raw_text": "unauthorized access on my account",
            "channel": "web_form",
            "customer_id": "CUST-9001",
            "classification_type": "escalation",
            "urgency": "critical",
            "confidence": 0.9,
            "branch_taken": "escalation",
            "remediation_steps": ["flagged for review"],
            "outputs": {},
            "status": "pending_review",
        }
    )

    monkeypatch.setattr(
        main,
        "run_override",
        lambda request_id, raw_text, classification: (
            ["Acknowledged receipt of complaint", "Escalated to senior handler"],
            {"draft_acknowledgement": "..."},
            "escalated",
            "complaint",
        ),
    )

    response = client.post(
        "/requests/req-override/override",
        json={"request_type": "complaint", "urgency": "high", "note": "actually a billing complaint"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overridden"] is True
    assert body["classification_type"] == "complaint"
    assert body["status"] == "escalated"
    assert body["original_classification"]["request_type"] == "escalation"
    assert body["original_classification"]["urgency"] == "critical"


def test_override_on_missing_request_returns_404(client):
    response = client.post(
        "/requests/does-not-exist/override",
        json={"request_type": "complaint", "urgency": "high"},
    )
    assert response.status_code == 404


def test_dashboard_stats_reflects_inserted_requests(client):
    db.insert_request(
        {
            "id": "req-a",
            "raw_text": "text",
            "channel": "email",
            "classification_type": "general_enquiry",
            "urgency": "low",
            "confidence": 0.95,
            "branch_taken": "general_enquiry",
            "remediation_steps": [],
            "outputs": {},
            "status": "resolved",
        }
    )

    response = client.get("/dashboard/stats")

    assert response.status_code == 200
    stats = response.json()
    assert stats["total_requests"] == 1
    assert stats["by_type"]["general_enquiry"] == 1

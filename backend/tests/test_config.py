from app.config import settings


def test_defaults_loaded():
    assert settings.confidence_threshold == 0.6
    assert settings.complaint_followup_hours == 2
    assert settings.service_request_sla_hours == 24


def test_department_routing_has_general_fallback():
    assert "general" in settings.department_routing

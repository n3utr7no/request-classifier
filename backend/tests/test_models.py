import pytest
from pydantic import ValidationError

from app.models import ClassificationResult


def test_valid_classification_result():
    result = ClassificationResult(
        request_type="complaint",
        urgency="high",
        confidence=0.9,
        sub_topic="billing",
        reasoning="Customer is unhappy about a duplicate charge.",
    )
    assert result.request_type == "complaint"
    assert result.confidence == 0.9


def test_rejects_invalid_request_type():
    with pytest.raises(ValidationError):
        ClassificationResult(
            request_type="not_a_real_type",
            urgency="high",
            confidence=0.9,
            reasoning="x",
        )


def test_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        ClassificationResult(
            request_type="complaint",
            urgency="high",
            confidence=1.5,
            reasoning="x",
        )

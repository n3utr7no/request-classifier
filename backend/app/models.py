from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

RequestType = Literal["complaint", "general_enquiry", "service_request", "escalation"]
Urgency = Literal["low", "medium", "high", "critical"]
Status = Literal["resolved", "in_progress", "escalated", "pending_review"]
Channel = Literal["email", "web_form", "file_upload"]


class RequestIn(BaseModel):
    raw_text: str
    channel: Channel = "email"
    customer_id: str


class ClassificationResult(BaseModel):
    request_type: RequestType
    urgency: Urgency
    confidence: float = Field(ge=0.0, le=1.0)
    sub_topic: Optional[str] = None
    reasoning: str


class OverrideIn(BaseModel):
    request_type: RequestType
    urgency: Urgency
    note: Optional[str] = None


class RequestRecord(BaseModel):
    id: str
    timestamp: datetime
    raw_text: str
    channel: str
    customer_id: str
    classification_type: RequestType
    urgency: Urgency
    confidence: float
    branch_taken: str
    remediation_steps: list[str]
    outputs: dict
    status: Status
    overridden: bool = False
    original_classification: Optional[dict] = None

from app.remediation import complaint, escalation, general_enquiry, human_review, service_request

BRANCH_HANDLERS = {
    "complaint": complaint.run,
    "general_enquiry": general_enquiry.run,
    "service_request": service_request.run,
    "escalation": escalation.run,
}

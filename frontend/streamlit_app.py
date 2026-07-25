import csv
import io
import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
DEFAULT_BATCH_SIZE = 4

st.set_page_config(page_title="Incoming Request Processing Workflow", layout="wide")
st.title("Incoming Request Processing Workflow")
st.caption("AI classification + branching remediation workflow")

TYPE_LABELS = {
    "complaint": "Complaint",
    "general_enquiry": "General Enquiry",
    "service_request": "Service Request",
    "escalation": "Escalation / Urgent",
    "human_review": "Human Review (low confidence)",
}
URGENCY_COLOR = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
CHANNEL_LABELS = {
    "email": "📧  Email",
    "web_form": "📝  Web Form",
    "file_upload": "📁  File Upload",
}

if "processing_log" not in st.session_state:
    st.session_state.processing_log = []
if "last_processed_file_id" not in st.session_state:
    st.session_state.last_processed_file_id = None


def render_outputs(outputs: dict) -> None:
    for key, value in outputs.items():
        label = key.replace("_", " ").title()
        st.markdown(f"**{label}:** {value}")


def render_result(record: dict) -> None:
    urgency = record["urgency"]
    st.subheader(
        f"{URGENCY_COLOR.get(urgency, '')} {TYPE_LABELS.get(record['classification_type'], record['classification_type'])}"
        f"  ·  urgency: {urgency}  ·  confidence: {record['confidence']:.2f}"
    )
    st.write(
        f"**Customer:** `{record.get('customer_id', '—')}`  ·  **Channel:** `{record.get('channel', '—')}`  ·  "
        f"**Status:** `{record['status']}`  ·  **Branch taken:** `{record['branch_taken']}`"
    )
    if record.get("overridden"):
        st.warning("This case was corrected via human override.")
        with st.expander("Original AI classification"):
            render_outputs(record["original_classification"])

    st.markdown("**Remediation steps triggered:**")
    for step in record["remediation_steps"]:
        st.markdown(f"- {step}")

    st.markdown("**Outputs:**")
    render_outputs(record["outputs"])


tab_customer, tab_backend, tab_dashboard, tab_review = st.tabs(
    ["Customer", "Backend", "Dashboard", "Review Queue"]
)

# --- Backend tab, part 1: processing-log placeholder created up front so the ---
# --- Customer tab's file-upload handler (below) can stream into it live.     ---
with tab_backend:
    st.subheader("Processing Log")
    st.caption("Live progress for batched file-upload processing.")
    log_area = st.empty()
    if st.session_state.processing_log:
        log_area.code("\n".join(st.session_state.processing_log), language=None)
    else:
        log_area.caption("No files processed yet.")


with tab_customer:
    st.write("Choose how this request came in — the intake form below changes to match.")
    channel = st.radio(
        "Intake mechanism",
        list(CHANNEL_LABELS.keys()),
        format_func=lambda c: CHANNEL_LABELS[c],
        horizontal=True,
        key="submit_channel",
    )

    if channel == "email":
        st.caption("Mirrors an inbound support mailbox: sender address, subject line, and body.")
        from_address = st.text_input("From", placeholder="jane.doe@example.com", key="email_from")
        subject = st.text_input("Subject", placeholder="Issue with my last invoice", key="email_subject")
        body = st.text_area("Body", height=150, placeholder="Type the email body here...", key="email_body")
        raw_text = f"From: {from_address}\nSubject: {subject}\n\n{body}".strip()

        if st.button("Process Request", type="primary", key="submit_email"):
            if not from_address.strip():
                st.error("Please enter a From address.")
            elif not body.strip():
                st.error("Please fill in the Body.")
            else:
                with st.spinner("Classifying and running remediation..."):
                    resp = requests.post(
                        f"{API_BASE}/requests",
                        json={"raw_text": raw_text, "channel": channel, "customer_id": from_address.strip()},
                    )
                if resp.ok:
                    render_result(resp.json())
                else:
                    st.error(f"Request failed: {resp.status_code} {resp.text}")

    elif channel == "web_form":
        st.caption("Mirrors a 'Contact Us' web form: customer picks a topic and types a message.")
        email = st.text_input("Email", placeholder="jane.doe@example.com", key="web_email")
        full_name = st.text_input("Full name (optional)", placeholder="Jane Doe", key="web_name")
        topic = st.selectbox("Topic", ["Billing", "Technical", "Account", "General", "Other"], key="web_topic")
        message = st.text_area(
            "Message", height=150, placeholder="Describe your issue or question...", key="web_message"
        )
        name_line = f"Submitted by: {full_name}\n" if full_name.strip() else ""
        raw_text = f"{name_line}Topic: {topic}\n\n{message}".strip()

        if st.button("Process Request", type="primary", key="submit_web_form"):
            if not email.strip():
                st.error("Please enter an Email.")
            elif not message.strip():
                st.error("Please fill in a message.")
            else:
                with st.spinner("Classifying and running remediation..."):
                    resp = requests.post(
                        f"{API_BASE}/requests",
                        json={"raw_text": raw_text, "channel": channel, "customer_id": email.strip()},
                    )
                if resp.ok:
                    render_result(resp.json())
                else:
                    st.error(f"Request failed: {resp.status_code} {resp.text}")

    elif channel == "file_upload":
        st.caption(
            "Mirrors a customer (or agent) uploading a CSV of one or more requests at once — "
            "columns: `customer_id, subject, body`. Select a file, then click Process Request "
            "to send it, in chunks of the batch size below."
        )
        st.number_input(
            "Batch size",
            min_value=1,
            max_value=50,
            value=st.session_state.get("batch_size_input", DEFAULT_BATCH_SIZE),
            step=1,
            key="batch_size_input",
            help=(
                "How many rows are sent for classification+remediation at a time. Changing this "
                "while a file is mid-processing does NOT affect that file — it only takes effect "
                "on the next file you upload."
            ),
        )
        uploaded_csv = st.file_uploader(
            "Upload CSV (customer_id, subject, body)", type="csv", key="csv_uploader"
        )

        process_clicked = st.button(
            "Process Request", type="primary", key="submit_file_upload", disabled=uploaded_csv is None
        )

        if uploaded_csv is None:
            pass
        elif not process_clicked and uploaded_csv.file_id == st.session_state.last_processed_file_id:
            st.caption(f"'{uploaded_csv.name}' was already processed. Click Process Request to send it again.")
        elif process_clicked:
            # Lock in the batch size for this file's entire run, right now — a later
            # change to the widget must only affect the *next* uploaded file.
            locked_batch_size = st.session_state["batch_size_input"]
            st.session_state.last_processed_file_id = uploaded_csv.file_id

            reader = csv.DictReader(io.StringIO(uploaded_csv.getvalue().decode("utf-8")))
            rows = [r for r in reader if r.get("body", "").strip()]

            st.session_state.processing_log.append(
                f"--- '{uploaded_csv.name}': {len(rows)} request(s) received, "
                f"batch size locked at {locked_batch_size} ---"
            )
            log_area.code("\n".join(st.session_state.processing_log), language=None)

            with st.spinner(f"Processing {len(rows)} request(s) in batches of {locked_batch_size}..."):
                for start in range(0, len(rows), locked_batch_size):
                    chunk = rows[start : start + locked_batch_size]
                    batch_num = start // locked_batch_size + 1
                    payload = [
                        {
                            "raw_text": (
                                f"Subject: {r['subject']}\n\n{r['body']}" if r.get("subject", "").strip() else r["body"]
                            ).strip(),
                            "channel": "file_upload",
                            "customer_id": r.get("customer_id") or "CUST-UNKNOWN",
                        }
                        for r in chunk
                    ]

                    st.session_state.processing_log.append(
                        f"Batch {batch_num}: rows {start + 1}-{start + len(chunk)} — processing..."
                    )
                    log_area.code("\n".join(st.session_state.processing_log), language=None)

                    resp = requests.post(f"{API_BASE}/requests/batch", json=payload)
                    if resp.ok:
                        error_count = sum(1 for r in resp.json() if "error" in r)
                        outcome = "done" if error_count == 0 else f"done, {error_count} error(s)"
                        st.session_state.processing_log[-1] += f" {outcome}"
                    else:
                        st.session_state.processing_log[-1] += f" FAILED ({resp.status_code})"
                    log_area.code("\n".join(st.session_state.processing_log), language=None)

            st.success(f"Processed {len(rows)} request(s) from '{uploaded_csv.name}'. See the Backend tab for the log.")


# --- Backend tab, part 2: rendered after any file-upload processing above, so ---
# --- newly created requests show up in the same run they were created in.    ---
with tab_backend:
    st.subheader("Received Requests")
    resp = requests.get(f"{API_BASE}/requests")
    if resp.ok:
        records = resp.json()
        st.caption(f"{len(records)} request(s) in the audit log, most recent first.")
        for record in records:
            channel_label = CHANNEL_LABELS.get(record.get("channel", ""), record.get("channel", "unknown"))
            header = (
                f"{channel_label}  ·  {record.get('customer_id', '—')}  ·  {record['timestamp']}  ·  "
                f"{record['status']}{' · OVERRIDDEN' if record.get('overridden') else ''}"
            )
            with st.expander(header):
                render_result(record)
    else:
        st.error("Could not load received requests.")


with tab_dashboard:
    st.write("Summary of request volumes by type and status.")
    resp = requests.get(f"{API_BASE}/dashboard/stats")
    if resp.ok:
        stats = resp.json()
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Requests", stats["total_requests"])
        col2.metric("Avg. Confidence", f"{stats['avg_confidence']:.2f}")
        col3.metric("Pending Review", stats["by_status"].get("pending_review", 0))

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**By Type**")
            if stats["by_type"]:
                st.bar_chart(stats["by_type"])
        with col_b:
            st.markdown("**By Status**")
            if stats["by_status"]:
                st.bar_chart(stats["by_status"])
    else:
        st.error("Could not load dashboard stats.")

with tab_review:
    st.write("Cases paused for human review (low-confidence classification or urgent escalation).")
    resp = requests.get(f"{API_BASE}/requests")
    if resp.ok:
        pending = [r for r in resp.json() if r["status"] == "pending_review"]
        if not pending:
            st.info("No cases currently pending review.")
        for record in pending:
            with st.expander(
                f"{record['timestamp']} · {record.get('customer_id', '—')} · {record['branch_taken']} · id={record['id'][:8]}"
            ):
                st.write(record["raw_text"])
                render_outputs(record["outputs"])
                st.markdown("**Provide corrected classification:**")
                new_type = st.selectbox(
                    "Request type",
                    ["complaint", "general_enquiry", "service_request", "escalation"],
                    key=f"type_{record['id']}",
                )
                new_urgency = st.selectbox(
                    "Urgency", ["low", "medium", "high", "critical"], key=f"urgency_{record['id']}"
                )
                note = st.text_input("Note (optional)", key=f"note_{record['id']}")
                if st.button("Submit Override", key=f"override_{record['id']}"):
                    override_resp = requests.post(
                        f"{API_BASE}/requests/{record['id']}/override",
                        json={"request_type": new_type, "urgency": new_urgency, "note": note},
                    )
                    if override_resp.ok:
                        st.success("Override applied. Refresh the tab to see the updated case.")
                        render_result(override_resp.json())
                    else:
                        st.error(f"Override failed: {override_resp.status_code} {override_resp.text}")
    else:
        st.error("Could not load review queue.")

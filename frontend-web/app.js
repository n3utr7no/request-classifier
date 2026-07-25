const API_BASE = "http://127.0.0.1:8000";
const DEFAULT_BATCH_SIZE = 4;

const TYPE_LABELS = {
  complaint: "Complaint",
  general_enquiry: "General Enquiry",
  service_request: "Service Request",
  escalation: "Escalation / Urgent",
  human_review: "Human Review",
};
const URGENCY_ICON = { low: "🟢", medium: "🟡", high: "🟠", critical: "🔴" };
const CHANNEL_LABELS = { email: "📧 Email", web_form: "📝 Web Form", file_upload: "📁 File Upload" };

// fixed render order, matches the validated adjacent-pair categorical ramp
const TYPE_ORDER = ["general_enquiry", "complaint", "service_request", "escalation"];
const TYPE_COLOR_VAR = {
  general_enquiry: "var(--series-enquiry)",
  complaint: "var(--series-complaint)",
  service_request: "var(--series-service)",
  escalation: "var(--series-escalation)",
};
const STATUS_ORDER = ["resolved", "in_progress", "escalated", "pending_review"];
const STATUS_LABELS = { resolved: "Resolved", in_progress: "In progress", escalated: "Escalated", pending_review: "Pending review" };
const STATUS_COLOR_VAR = {
  resolved: "var(--status-good)",
  in_progress: "var(--status-warning)",
  escalated: "var(--status-serious)",
  pending_review: "var(--status-critical)",
};

/* ============================================================ top-level nav */

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const view = btn.dataset.view;
    document.getElementById("view-customer").hidden = view !== "customer";
    document.getElementById("view-backend").hidden = view !== "backend";
    if (view === "backend") refreshCurrentBackendSubview();
  });
});

/* ============================================================ customer: channel switch */

document.querySelectorAll("#view-customer .channel-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#view-customer .channel-btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const channel = btn.dataset.channel;
    document.querySelectorAll(".channel-form").forEach((f) => (f.hidden = f.dataset.form !== channel));
  });
});

/* ============================================================ result rendering */

function renderResult(record) {
  const panel = document.getElementById("result-panel");
  panel.hidden = false;
  const urgency = record.urgency;
  const typeLabel = TYPE_LABELS[record.classification_type] || record.classification_type;

  let overrideBlock = "";
  if (record.overridden) {
    overrideBlock = `
      <p class="result-meta">⚠️ This case was corrected via human override. Original AI classification:
        <code>${escapeHtml(JSON.stringify(record.original_classification))}</code></p>`;
  }

  panel.innerHTML = `
    <h3>${URGENCY_ICON[urgency] || ""} ${typeLabel} <span class="mono" style="font-size:14px; color: var(--ink-muted);">· urgency: ${urgency} · confidence: ${record.confidence.toFixed(2)}</span></h3>
    <p class="result-meta">
      <strong>Customer:</strong> <code>${escapeHtml(record.customer_id || "-")}</code> ·
      <strong>Channel:</strong> <code>${escapeHtml(record.channel || "-")}</code> ·
      <strong>Status:</strong> <code>${escapeHtml(record.status)}</code> ·
      <strong>Branch:</strong> <code>${escapeHtml(record.branch_taken)}</code>
    </p>
    ${overrideBlock}
    <p><strong>Remediation steps triggered:</strong></p>
    <ul class="result-steps">${record.remediation_steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
    <p><strong>Outputs:</strong></p>
    <div class="result-outputs">${escapeHtml(JSON.stringify(record.outputs, null, 2))}</div>
  `;
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ============================================================ single-submit forms */

async function submitSingle(payload, submitBtn) {
  submitBtn.disabled = true;
  const originalText = submitBtn.textContent;
  submitBtn.textContent = "Processing…";
  try {
    const resp = await fetch(`${API_BASE}/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      alert(`Request failed (${resp.status}): ${text}`);
      return;
    }
    renderResult(await resp.json());
  } catch (err) {
    alert(`Network error: ${err.message}. Is the backend running at ${API_BASE}?`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  }
}

document.querySelector('[data-form="email"]').addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target;
  const from = form.from_address.value.trim();
  const subject = form.subject.value.trim();
  const body = form.body.value.trim();
  if (!from || !body) return alert("Please fill in From and Body.");
  const rawText = `From: ${from}\nSubject: ${subject}\n\n${body}`.trim();
  submitSingle({ raw_text: rawText, channel: "email", customer_id: from }, form.querySelector("button"));
});

document.querySelector('[data-form="web_form"]').addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target;
  const email = form.email.value.trim();
  const fullName = form.full_name.value.trim();
  const topic = form.topic.value;
  const message = form.message.value.trim();
  if (!email || !message) return alert("Please fill in Email and Message.");
  const nameLine = fullName ? `Submitted by: ${fullName}\n` : "";
  const rawText = `${nameLine}Topic: ${topic}\n\n${message}`.trim();
  submitSingle({ raw_text: rawText, channel: "web_form", customer_id: email }, form.querySelector("button"));
});

/* ============================================================ file upload: CSV batch */

let processingLog = [];
let lastFileSignature = null;

function logAreaEl() {
  return document.getElementById("log-area");
}
function pushLog(line) {
  processingLog.push(line);
  renderLog();
}
function updateLastLog(suffix) {
  processingLog[processingLog.length - 1] += suffix;
  renderLog();
}
function renderLog() {
  logAreaEl().textContent = processingLog.length ? processingLog.join("\n") : "No files processed yet.";
  logAreaEl().scrollTop = logAreaEl().scrollHeight;
}

// Minimal RFC4180 CSV parser: handles quoted fields, embedded commas/newlines, "" escaping.
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((v) => v !== "")) rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }

  if (!rows.length) return [];
  const headers = rows[0].map((h) => h.trim());
  return rows.slice(1).map((r) => Object.fromEntries(headers.map((h, i) => [h, (r[i] || "").trim()])));
}

const dropzone = document.getElementById("dropzone");
const csvInput = document.getElementById("csv-input");
["dragover", "dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.toggle("is-dragover", evt === "dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleCsvFile(file);
});
csvInput.addEventListener("change", () => {
  if (csvInput.files[0]) handleCsvFile(csvInput.files[0]);
});

async function handleCsvFile(file) {
  const signature = `${file.name}:${file.size}:${file.lastModified}`;
  if (signature === lastFileSignature) return; // already processed this exact file
  lastFileSignature = signature;

  document.getElementById("dropzone-sub").textContent = `Processing "${file.name}"…`;

  // Batch size is locked in NOW, for this file's entire run.
  // A later change to the input only takes effect on the next file uploaded.
  const lockedBatchSize = parseInt(document.getElementById("batch-size-input").value, 10) || DEFAULT_BATCH_SIZE;

  const text = await file.text();
  const rows = parseCsv(text).filter((r) => (r.body || "").trim());

  pushLog(`--- '${file.name}': ${rows.length} request(s) received, batch size locked at ${lockedBatchSize} ---`);

  let totalErrors = 0;
  for (let start = 0; start < rows.length; start += lockedBatchSize) {
    const chunk = rows.slice(start, start + lockedBatchSize);
    const batchNum = Math.floor(start / lockedBatchSize) + 1;
    const payload = chunk.map((r) => ({
      raw_text: (r.subject ? `Subject: ${r.subject}\n\n${r.body}` : r.body).trim(),
      channel: "file_upload",
      customer_id: r.customer_id || "CUST-UNKNOWN",
    }));

    pushLog(`Batch ${batchNum}, rows ${start + 1}-${start + chunk.length}: processing...`);
    try {
      const resp = await fetch(`${API_BASE}/requests/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        const results = await resp.json();
        const errors = results.filter((r) => r.error).length;
        totalErrors += errors;
        updateLastLog(errors === 0 ? " done" : ` done, ${errors} error(s)`);
      } else {
        updateLastLog(` FAILED (${resp.status})`);
      }
    } catch (err) {
      updateLastLog(` FAILED (network error)`);
    }
  }

  document.getElementById("dropzone-sub").textContent = `"${file.name}": ${rows.length} request(s) processed${totalErrors ? `, ${totalErrors} error(s)` : ""}.`;
  if (!document.getElementById("view-backend").hidden) refreshCurrentBackendSubview();
}

/* ============================================================ backend: sub-tab switch */

document.querySelectorAll("#view-backend .channel-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#view-backend .channel-btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const subview = btn.dataset.subview;
    document.getElementById("subview-requests").hidden = subview !== "requests";
    document.getElementById("subview-dashboard").hidden = subview !== "dashboard";
    document.getElementById("subview-review").hidden = subview !== "review";
    document.getElementById("subview-escalated").hidden = subview !== "escalated";
    refreshCurrentBackendSubview();
  });
});

function refreshCurrentBackendSubview() {
  const active = document.querySelector("#view-backend .channel-btn.is-active").dataset.subview;
  if (active === "requests") loadRequests();
  else if (active === "dashboard") loadDashboard();
  else if (active === "review") loadReviewQueue();
  else if (active === "escalated") loadEscalated();
}

/* ---- requests list ---- */

async function loadRequests() {
  const list = document.getElementById("requests-list");
  const countEl = document.getElementById("requests-count");
  try {
    const resp = await fetch(`${API_BASE}/requests`);
    const records = await resp.json();
    countEl.textContent = `${records.length} request(s) in the audit log, most recent first.`;
    list.innerHTML = records.length ? records.map(requestCardHtml).join("") : `<p class="empty-note">No requests yet.</p>`;
  } catch (err) {
    list.innerHTML = `<p class="empty-note">Could not load requests. Is the backend running?</p>`;
  }
}

function requestCardHtml(record) {
  const channelLabel = CHANNEL_LABELS[record.channel] || record.channel;
  const overridden = record.overridden ? " · OVERRIDDEN" : "";
  const body = prettyBodyHtml(record);
  return `
    <details class="request-card">
      <summary>
        <span class="channel-tag">${channelLabel}</span>
        <span class="cust-id">${escapeHtml(record.customer_id || "-")}</span>
        <span>${record.timestamp}</span>
        <span class="pill status-${record.status}"><span class="pill-dot"></span>${STATUS_LABELS[record.status] || record.status}</span>
        ${overridden}
      </summary>
      <div class="request-card-body">${body}</div>
    </details>`;
}

function prettyBodyHtml(record) {
  const typeLabel = TYPE_LABELS[record.classification_type] || record.classification_type;
  return `
    <p><strong>${URGENCY_ICON[record.urgency] || ""} ${typeLabel}</strong> · urgency: ${record.urgency} · confidence: ${record.confidence.toFixed(2)}</p>
    <p class="result-meta">${escapeHtml(record.raw_text)}</p>
    <p><strong>Steps:</strong></p>
    <ul class="result-steps">${record.remediation_steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
    <p><strong>Outputs:</strong></p>
    <div class="result-outputs">${escapeHtml(JSON.stringify(record.outputs, null, 2))}</div>
  `;
}

/* ---- dashboard ---- */

async function loadDashboard() {
  try {
    const resp = await fetch(`${API_BASE}/dashboard/stats`);
    const stats = await resp.json();
    document.getElementById("stat-total").textContent = stats.total_requests;
    document.getElementById("stat-confidence").textContent = stats.avg_confidence.toFixed(2);
    document.getElementById("stat-pending").textContent = stats.by_status.pending_review || 0;

    renderBarChart("chart-type", TYPE_ORDER, stats.by_type, (t) => TYPE_LABELS[t] || t, (t) => TYPE_COLOR_VAR[t]);
    renderBarChart("chart-status", STATUS_ORDER, stats.by_status, (s) => STATUS_LABELS[s] || s, (s) => STATUS_COLOR_VAR[s]);
  } catch (err) {
    document.getElementById("stat-total").textContent = "-";
  }
}

function renderBarChart(elId, order, counts, labelFn, colorFn) {
  const el = document.getElementById(elId);
  const max = Math.max(1, ...order.map((k) => counts[k] || 0));
  el.innerHTML = order
    .map((key) => {
      const value = counts[key] || 0;
      const pct = Math.round((value / max) * 100);
      return `
        <div class="bar-row">
          <span class="bar-name"><span class="pill-dot" style="background:${colorFn(key)}"></span>${labelFn(key)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%; background:${colorFn(key)}"></div></div>
          <span class="bar-value">${value}</span>
        </div>`;
    })
    .join("");
}

/* ---- review queue ---- */

async function loadReviewQueue() {
  const list = document.getElementById("review-list");
  try {
    const resp = await fetch(`${API_BASE}/requests`);
    const records = await resp.json();
    const pending = records.filter((r) => r.status === "pending_review");
    list.innerHTML = pending.length
      ? pending.map(reviewCardHtml).join("")
      : `<p class="empty-note">No cases currently pending review.</p>`;
    pending.forEach((r) => wireOverrideForm(r.id));
  } catch (err) {
    list.innerHTML = `<p class="empty-note">Could not load review queue.</p>`;
  }
}

function reviewCardHtml(record) {
  return `
    <details class="request-card" open>
      <summary>
        <span class="cust-id">${escapeHtml(record.customer_id || "-")}</span>
        <span>${record.branch_taken}</span>
        <span>${record.timestamp}</span>
      </summary>
      <div class="request-card-body">
        <p class="result-meta">${escapeHtml(record.raw_text)}</p>
        <div class="result-outputs">${escapeHtml(JSON.stringify(record.outputs, null, 2))}</div>
        <form class="channel-form" data-override-id="${record.id}" style="margin-top:16px;">
          <div class="field-row">
            <label class="field">
              <span>Corrected type</span>
              <select name="request_type">
                <option value="complaint">Complaint</option>
                <option value="general_enquiry">General Enquiry</option>
                <option value="service_request">Service Request</option>
                <option value="escalation">Escalation</option>
              </select>
            </label>
            <label class="field">
              <span>Corrected urgency</span>
              <select name="urgency">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
          </div>
          <label class="field">
            <span>Note (optional)</span>
            <input type="text" name="note" placeholder="Why you're overriding this" />
          </label>
          <button class="btn-primary" type="submit">Submit override</button>
        </form>
        <div class="override-result"></div>
      </div>
    </details>`;
}

function wireOverrideForm(recordId) {
  const form = document.querySelector(`form[data-override-id="${recordId}"]`);
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button");
    btn.disabled = true;
    btn.textContent = "Submitting…";
    try {
      const resp = await fetch(`${API_BASE}/requests/${recordId}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_type: form.request_type.value,
          urgency: form.urgency.value,
          note: form.note.value,
        }),
      });
      if (resp.ok) {
        const record = await resp.json();
        form.closest(".request-card-body").querySelector(".override-result").innerHTML =
          `<p class="result-meta">✅ Override applied: status is now <code>${record.status}</code>, branch <code>${record.branch_taken}</code>.</p>`;
        form.remove();
      } else {
        alert(`Override failed: ${resp.status} ${await resp.text()}`);
      }
    } catch (err) {
      alert(`Network error: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "Submit override";
    }
  });
}

/* ---- human-escalated requests ---- */

async function loadEscalated() {
  const list = document.getElementById("escalated-list");
  const countEl = document.getElementById("escalated-count");
  try {
    const resp = await fetch(`${API_BASE}/requests`);
    const records = await resp.json();
    // Anything the AI ever routed through the Escalation branch: either it's
    // still classified that way now, or it was originally escalation before
    // a human override corrected it to something else.
    const escalated = records.filter(
      (r) => r.classification_type === "escalation" || (r.original_classification && r.original_classification.request_type === "escalation")
    );
    countEl.textContent = `${escalated.length} request(s) ever flagged as an urgent escalation.`;
    list.innerHTML = escalated.length
      ? escalated.map(escalatedCardHtml).join("")
      : `<p class="empty-note">No escalations recorded yet.</p>`;
  } catch (err) {
    list.innerHTML = `<p class="empty-note">Could not load escalated requests.</p>`;
  }
}

function escalatedCardHtml(record) {
  const wasOverriddenAway = record.classification_type !== "escalation";
  return `
    <details class="request-card">
      <summary>
        <span class="cust-id">${escapeHtml(record.customer_id || "-")}</span>
        <span>${record.timestamp}</span>
        <span class="pill status-${record.status}"><span class="pill-dot"></span>${STATUS_LABELS[record.status] || record.status}</span>
        ${wasOverriddenAway ? `<span class="pill status-resolved">reclassified by human</span>` : ""}
      </summary>
      <div class="request-card-body">${prettyBodyHtml(record)}</div>
    </details>`;
}

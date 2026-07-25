import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer_id TEXT NOT NULL DEFAULT '',
    classification_type TEXT NOT NULL,
    urgency TEXT NOT NULL,
    confidence REAL NOT NULL,
    branch_taken TEXT NOT NULL,
    remediation_steps TEXT NOT NULL,   -- JSON list[str]
    outputs TEXT NOT NULL,             -- JSON dict
    status TEXT NOT NULL,
    overridden INTEGER NOT NULL DEFAULT 0,
    original_classification TEXT       -- JSON dict, nullable
);
"""


def get_connection() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(SCHEMA)
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(requests_log)")}
        if "customer_id" not in existing_columns:
            conn.execute("ALTER TABLE requests_log ADD COLUMN customer_id TEXT NOT NULL DEFAULT ''")


def insert_request(record: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO requests_log (
                id, timestamp, raw_text, channel, customer_id, classification_type, urgency,
                confidence, branch_taken, remediation_steps, outputs, status,
                overridden, original_classification
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                record["raw_text"],
                record["channel"],
                record.get("customer_id", ""),
                record["classification_type"],
                record["urgency"],
                record["confidence"],
                record["branch_taken"],
                json.dumps(record["remediation_steps"]),
                json.dumps(record["outputs"]),
                record["status"],
                int(record.get("overridden", False)),
                json.dumps(record["original_classification"])
                if record.get("original_classification")
                else None,
            ),
        )


def update_request(request_id: str, **fields: Any) -> None:
    if not fields:
        return
    json_fields = {"remediation_steps", "outputs", "original_classification"}
    set_clauses = []
    values: list[Any] = []
    for key, value in fields.items():
        set_clauses.append(f"{key} = ?")
        if key in json_fields and value is not None:
            value = json.dumps(value)
        if key == "overridden":
            value = int(value)
        values.append(value)
    values.append(request_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE requests_log SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["remediation_steps"] = json.loads(d["remediation_steps"])
    d["outputs"] = json.loads(d["outputs"])
    d["overridden"] = bool(d["overridden"])
    d["original_classification"] = (
        json.loads(d["original_classification"]) if d["original_classification"] else None
    )
    return d


def get_request(request_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM requests_log WHERE id = ?", (request_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_requests(limit: int = 200) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM requests_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def dashboard_stats() -> dict[str, Any]:
    with get_connection() as conn:
        by_type = conn.execute(
            "SELECT classification_type, COUNT(*) as count FROM requests_log GROUP BY classification_type"
        ).fetchall()
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM requests_log GROUP BY status"
        ).fetchall()
        avg_confidence_row = conn.execute(
            "SELECT AVG(confidence) as avg_confidence FROM requests_log"
        ).fetchone()
        total = conn.execute("SELECT COUNT(*) as count FROM requests_log").fetchone()

    return {
        "total_requests": total["count"],
        "by_type": {row["classification_type"]: row["count"] for row in by_type},
        "by_status": {row["status"]: row["count"] for row in by_status},
        "avg_confidence": avg_confidence_row["avg_confidence"] or 0.0,
    }

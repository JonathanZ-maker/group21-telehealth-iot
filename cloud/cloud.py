"""
cloud/cloud.py
Cloud API Service — Flask + MongoDB Atlas
Owner: YYX
Course: ELEC0138 Security and Privacy — Group 21

Routes:
  POST /enroll    — mint a device JWT (intentionally unauthenticated)
  POST /ingest    — receive one heart-rate packet (JWT + Pydantic protected)
  GET  /readings  — clinician read endpoint (JWT + different scope)

Resilience:
  rollback(since_ts) — delete all records ingested at or after a given unix timestamp
  POST /rollback  — admin endpoint to trigger rollback (for demo)
"""

import os
import time
import logging

from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv

from zym_defense.cloud_auth   import require_jwt, issue_token
from zym_defense.cloud_schema import validate_payload

# ── Setup ─────────────────────────────────────────────────────────────────────

load_dotenv()  # reads .env file for MONGO_URI, JWT_SECRET, etc.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# MongoDB connection — URI must be set in .env, never hardcoded
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI not set. Copy .env.example → .env and fill it in.")

client = MongoClient(MONGO_URI)
db = client.telehealth          # database name: telehealth
readings_col = db.readings      # collection name: readings


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/enroll")
def enroll():
    """
    Mint a JWT for a device.
    Intentionally unauthenticated — any device can self-enroll.
    Scope granted: ingest:write only (cannot read back data).
    This is the entry point for Attack A2.3 (scope escalation).
    """
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id", "unknown")

    token = issue_token(device_id, ["ingest:write"])

    log.info("Enrolled device=%s", device_id)
    return jsonify({"token": token}), 200


@app.post("/ingest")
@require_jwt("ingest:write")                        # ZYM: rejects missing / wrong-scope tokens → 401
def ingest():
    """
    Receive one heart-rate packet from the gateway.
    Protected by:
      - ZYM's JWT middleware (@require_jwt)
      - ZYM's Pydantic schema (validate_payload)
    On success: insert into MongoDB with an _ingested_at timestamp.
    """
    record, err = validate_payload(request)          # ZYM: rejects NoSQL operators / bad types → 400
    if err:
        log.warning("Schema violation on /ingest: %s", err)
        return err                                   # err is already a Flask response (400)

    record["_ingested_at"] = int(time.time())        # used by rollback()

    readings_col.insert_one(record)
    log.info("Stored record patient_id=%s ts=%s", record.get("patient_id"), record.get("timestamp"))

    return jsonify({"status": "stored"}), 200


@app.get("/readings")
@require_jwt("readings:read")                        # ZYM: different scope — ingest token rejected → 401
def readings():
    """
    Return up to 100 stored readings.
    Target endpoint for Attack A2.1 (no token) and A2.3 (wrong-scope token).
    """
    cursor = readings_col.find({}, {"_id": 0}).limit(100)
    records = list(cursor)

    log.info("Readings fetched, count=%d", len(records))
    return jsonify({"records": records}), 200


# ── Resilience: data rollback ─────────────────────────────────────────────────

def rollback(since_ts: int) -> int:
    """
    Delete all records ingested at or after since_ts (unix seconds).
    Returns the number of deleted documents.

    Usage example (video demo):
        rollback(since_ts=1713358800)   # revert everything after 14:00
    """
    result = readings_col.delete_many({"_ingested_at": {"$gte": since_ts}})
    log.warning("ROLLBACK: deleted %d records ingested since ts=%d", result.deleted_count, since_ts)
    return result.deleted_count


@app.post("/rollback")
def rollback_endpoint():
    """
    Admin endpoint to trigger a rollback.
    For the video demo: call this after the anomaly detector flags a poisoned run.

    Example:
        curl -X POST http://localhost:5000/rollback \\
             -H "Content-Type: application/json" \\
             -d '{"since_ts": 1713358800}'
    """
    body = request.get_json(silent=True) or {}
    since_ts = body.get("since_ts")

    if since_ts is None:
        return jsonify({"error": "since_ts is required"}), 400

    try:
        since_ts = int(since_ts)
    except (ValueError, TypeError):
        return jsonify({"error": "since_ts must be an integer unix timestamp"}), 400

    deleted = rollback(since_ts)
    return jsonify({"status": "rolled_back", "deleted": deleted}), 200


# ── Health check (optional, useful for debugging) ─────────────────────────────

@app.get("/health")
def health():
    """Quick liveness probe — no auth required."""
    try:
        client.admin.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return jsonify({"status": "ok", "mongodb": db_status}), 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting cloud.py on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
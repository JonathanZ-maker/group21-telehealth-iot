"""
cloud/cloud.py
Owner: YYX

Overview:
  - Flask service backed by MongoDB Atlas that ingests heart-rate readings from the edge gateway and exposes them to clinician-side consumers.
  - All data-mutating and data-reading endpoints are protected by JWT middleware (cloud_auth.py) and Pydantic schema (cloud_schema.py), 
    providing scope-based access control and NoSQL-injection defence.
  - Served by Waitress, a production-grade WSGI server (not Flask's built-in development server).
  - Persists an _ingested_at timestamp alongside every record to support rollback when an upstream anomaly detector flags a poisoned run.
  - Acts as the target for Attack 2 (NoSQL injection and unauthorised exfiltration), with the undefended counterpart in cloud_nodefense.py.
"""

import os
import time
import logging

from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv
from zym_defense.cloud_auth   import require_jwt, issue_token
from zym_defense.cloud_schema import validate_payload

# Setup
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI not set. Copy .env.example → .env and fill it in.")

client = MongoClient(MONGO_URI)
db = client.telehealth
readings_col = db.readings


# Print admin token on startup
def _print_admin_token() -> None:
    token = issue_token("admin", ["admin:write", "readings:read", "ingest:write"])
    log.info("=" * 60)
    log.info("ADMIN TOKEN (copy for /rollback demo):")
    log.info("%s", token)
    log.info("=" * 60)

_print_admin_token()


# Routes 
@app.post("/enroll")
def enroll():
    """
    Mint a JWT for a device.
    """
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id", "unknown")

    token = issue_token(device_id, ["ingest:write"])

    log.info("Enrolled device=%s", device_id)
    return jsonify({"token": token}), 200


@app.post("/_debug_clinician_token")
def _debug_clinician_token():
    """
    Simulating a leaked clinician token.
    """
    body = request.get_json(silent=True) or {}
    subject = body.get("subject", "stolen-clinician-token")

    token = issue_token(subject, ["readings:read"])

    log.warning("DEMO: issued stolen-clinician-style token sub=%s (NOT FOR PROD)", subject)
    return jsonify({"token": token}), 200


@app.post("/ingest")
@require_jwt("ingest:write")
def ingest():
    record, err = validate_payload(request)
    if err:
        log.warning("Schema violation on /ingest: %s", err)
        return err

    record["_ingested_at"] = int(time.time())

    readings_col.insert_one(record)
    log.info("Stored record patient_id=%s ts=%s", record.get("patient_id"), record.get("timestamp"))

    return jsonify({"status": "stored"}), 200


@app.get("/readings")
@require_jwt("readings:read")
def readings():
    cursor = readings_col.find({}, {"_id": 0, "_ingested_at": 0}).limit(100)
    records = list(cursor)

    log.info("Readings fetched, count=%d", len(records))
    return jsonify({"records": records}), 200


@app.post("/search_patient")
@require_jwt("readings:read")
def search_patient():
    """
    Look up readings for a single patient — clinician-style lookup.
    """
    raw = request.get_json(silent=True) or {}

    # ZYM's schema gate — rejects {"$ne": null} as non-string
    record, err = validate_payload_for_query(raw)
    if err:
        log.warning("Schema violation on /search_patient: %s", err)
        return err

    # If we reach here, patient_id is a clean string.
    cursor = readings_col.find(
        {"patient_id": record["patient_id"]},
        {"_id": 0, "_ingested_at": 0},
    ).limit(100)
    records = list(cursor)

    log.info("Search hit patient_id=%s count=%d", record["patient_id"], len(records))
    return jsonify({"records": records, "matched": len(records)}), 200


def validate_payload_for_query(raw: dict):
    """
    Reuse ZYM's StrictStr / extra=forbid Pydantic schema to validate the
    body of /search_patient. 
    """
    from zym_defense.cloud_schema import HeartRateRecord
    from pydantic import ValidationError

    candidate = {
        "patient_id": raw.get("patient_id"),
        "timestamp":  1,
        "heart_rate": 70.0,
    }

    try:
        rec = HeartRateRecord(**candidate)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(x) for x in first.get("loc", ()))
        code  = first.get("type", "validation_error")
        log.warning("BLOCK /search_patient field=%s code=%s peer=%s",
                    field, code, request.remote_addr)
        return None, (jsonify({
            "error": "schema_violation",
            "field": field,
            "code":  code,
        }), 400)

    return {"patient_id": rec.patient_id}, None


# Resilience: data rollback
def rollback(since_ts: int) -> int:
    result = readings_col.delete_many({"_ingested_at": {"$gte": since_ts}})
    log.warning("ROLLBACK: deleted %d records ingested since ts=%d",
                result.deleted_count, since_ts)
    return result.deleted_count


@app.post("/rollback")
@require_jwt("admin:write")
def rollback_endpoint():
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


# Health check
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        count = readings_col.count_documents({})
        db_status = "connected"
    except Exception as e:
        count = 0
        db_status = f"error: {e}"

    return jsonify({"status": "ok", "mongodb": db_status, "record_count": count}), 200


# Entry point 
if __name__ == "__main__":
    from waitress import serve
    log.info("Starting cloud.py on port 5000 (Waitress WSGI server)")
    serve(app, host="0.0.0.0", port=5000)
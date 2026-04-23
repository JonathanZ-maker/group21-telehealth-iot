"""
cloud/cloud_nodefense.py
UNDEFENDED version of cloud.py.
Owner: YYX

Structural diff vs cloud.py:
  /ingest          — @require_jwt removed, validate_payload removed
  /readings        — @require_jwt removed
  /search_patient  — @require_jwt removed, validate_payload_for_query removed
                     (user input flows directly into the Mongo query filter)
  /rollback        — @require_jwt removed (for convenience during demo)
"""

import os
import time
import logging

from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv
from zym_defense.cloud_auth import issue_token  # still used for /enroll + demo

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


# Print admin token on startup (for rollback demo) 
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
    DEMO-ONLY endpoint simulating a leaked clinician token.
    """
    body = request.get_json(silent=True) or {}
    subject = body.get("subject", "stolen-clinician-token")

    token = issue_token(subject, ["readings:read"])

    log.warning("DEMO: issued stolen-clinician-style token sub=%s (NOT FOR PROD)", subject)
    return jsonify({"token": token}), 200


@app.post("/ingest")
# @require_jwt("ingest:write")     ← DEFENCE REMOVED (JWT gate)
def ingest():
    """
    UNDEFENDED: no JWT, no schema validation.
    Accepts any JSON and writes it straight into MongoDB.
    An attacker can submit malformed / operator-laced payloads freely.
    """
    # record, err = validate_payload(request)   ← DEFENCE REMOVED (Pydantic)
    # if err:
    #     log.warning("Schema violation on /ingest: %s", err)
    #     return err

    record = request.get_json(silent=True) or {}
    record["_ingested_at"] = int(time.time())

    readings_col.insert_one(record)
    log.info("Stored record patient_id=%s ts=%s",
             record.get("patient_id"), record.get("timestamp"))

    return jsonify({"status": "stored"}), 200


@app.get("/readings")
# @require_jwt("readings:read")    ← DEFENCE REMOVED (JWT gate)
def readings():
    """
    UNDEFENDED: no JWT. Anyone can dump up to 100 records.
    Target endpoint for Attack A2.1 and A2.3.
    """
    cursor = readings_col.find({}, {"_id": 0, "_ingested_at": 0}).limit(100)
    records = list(cursor)

    log.info("Readings fetched, count=%d", len(records))
    return jsonify({"records": records}), 200


@app.post("/search_patient")
# @require_jwt("readings:read")    ← DEFENCE REMOVED (JWT gate)
def search_patient():
    """
    UNDEFENDED: no JWT, no schema validation.

    User input flows DIRECTLY into the Mongo query filter — the TRUE
    NoSQL injection target (CWE-943).

    Example attack payload:
        {"patient_id": {"$ne": null}}
    → Mongo interprets $ne as an operator and returns every record.
    """
    raw = request.get_json(silent=True) or {}

    # record, err = validate_payload_for_query(raw)   ← DEFENCE REMOVED (Pydantic)
    # if err:
    #     log.warning("Schema violation on /search_patient: %s", err)
    #     return err

    patient_id = raw.get("patient_id")                # raw input, no sanitisation

    cursor = readings_col.find(
        {"patient_id": patient_id},
        {"_id": 0, "_ingested_at": 0},
    ).limit(100)
    records = list(cursor)

    log.info("Search hit patient_id=%s count=%d", patient_id, len(records))
    return jsonify({"records": records, "matched": len(records)}), 200


# Resilience: data rollback
def rollback(since_ts: int) -> int:
    result = readings_col.delete_many({"_ingested_at": {"$gte": since_ts}})
    log.warning("ROLLBACK: deleted %d records ingested since ts=%d",
                result.deleted_count, since_ts)
    return result.deleted_count


@app.post("/rollback")
# @require_jwt("admin:write")      ← DEFENCE REMOVED (JWT gate)
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
    """Quick liveness probe — no auth required. Shows DB record count."""
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
    log.warning("=" * 60)
    log.warning("  STARTING UNDEFENDED CLOUD SERVICE — DEMO ONLY")
    log.warning("  All defences disabled for attack demonstration")
    log.warning("=" * 60)
    log.info("Starting cloud_nodefense.py on port 5000 (Waitress WSGI server)")
    serve(app, host="0.0.0.0", port=5000)
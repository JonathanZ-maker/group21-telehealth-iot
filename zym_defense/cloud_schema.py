"""
cloud_schema.py
================
Strong-typed input validation middleware for the telehealth cloud API.

Defence target
--------------
Attack 2: NoSQL injection via operator-embedded JSON payloads
(e.g. {"patient_id": {"$ne": null}}) which MongoDB would otherwise
interpret as a query operator, enabling auth bypass and full-database
exfiltration.

Design principle
----------------
Fail-closed, schema-first validation at the earliest possible point of
the request pipeline. Any payload that does not conform to the declared
primitive types is rejected with HTTP 400 before it ever reaches the
database driver.

Author: ZYM (Group 21)
Module: Defence 2 — Cloud layer / Input sanitisation
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from flask import Request, jsonify
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr, ValidationError, field_validator

# ---------------------------------------------------------------------------
# Logger — writes to stderr; also captured to file by the gateway's root logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("zym.cloud_schema")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] [SCHEMA] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Core schema — mirrors the wearable.py payload exactly
# ---------------------------------------------------------------------------
class HeartRateRecord(BaseModel):
    """
    Canonical schema for a single heart-rate telemetry record uploaded by
    the edge gateway. Uses Strict* types so Pydantic refuses implicit
    coercion (e.g. "123" -> 123) AND refuses dict-typed values outright,
    which is what stops NoSQL operator injection.
    """

    # Strict types — refuse coercion; dict payload raises ValidationError
    patient_id: StrictStr = Field(..., min_length=1, max_length=64)
    timestamp: StrictInt = Field(..., ge=0)          # unix seconds
    heart_rate: StrictFloat = Field(..., ge=20.0, le=250.0)  # human-plausible BPM

    # Optional fields produced by upstream modules
    nonce: StrictStr | None = Field(default=None, max_length=128)
    hmac_sig: StrictStr | None = Field(default=None, max_length=128)

    # Forbid any extra field — blocks smuggling of $where / $expr etc.
    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @field_validator("patient_id")
    @classmethod
    def _reject_operator_prefixes(cls, v: str) -> str:
        """Defence-in-depth: even a string field must not start with '$'."""
        if v.startswith("$"):
            raise ValueError("patient_id must not start with '$'")
        return v


# ---------------------------------------------------------------------------
# Flask-compatible validator helper
# ---------------------------------------------------------------------------
def validate_payload(req: Request) -> Tuple[Dict[str, Any] | None, Tuple[Any, int] | None]:
    """
    Validate a Flask request body against HeartRateRecord.

    Returns
    -------
    (record_dict, None)       on success
    (None, (response, 400))   on failure — response is a Flask jsonify tuple
                              ready to be returned by the route handler.

    Usage in cloud.py (YYX's file — a one-liner injection point)::

        from zym_defense.cloud_schema import validate_payload

        @app.route("/ingest", methods=["POST"])
        @require_jwt                       # from cloud_auth.py
        def ingest():
            record, err = validate_payload(request)
            if err:
                return err                 # 400 + structured reason
            db.readings.insert_one(record)
            return {"status": "ok"}, 200
    """
    raw = req.get_json(silent=True)

    if raw is None:
        logger.warning("BLOCK  reason=empty_or_non_json_body  peer=%s", req.remote_addr)
        return None, (jsonify({
            "error": "invalid_payload",
            "detail": "request body must be valid JSON",
        }), 400)

    # Top-level must be an object. List payloads are rejected outright.
    if not isinstance(raw, dict):
        logger.warning("BLOCK  reason=non_object_payload  type=%s  peer=%s",
                       type(raw).__name__, req.remote_addr)
        return None, (jsonify({
            "error": "invalid_payload",
            "detail": "top-level JSON must be an object",
        }), 400)

    try:
        record = HeartRateRecord(**raw)
    except ValidationError as exc:
        # Summarise — do NOT leak full error list to the attacker
        first = exc.errors()[0]
        field = ".".join(str(x) for x in first.get("loc", ()))
        code = first.get("type", "validation_error")
        logger.warning(
            "BLOCK  reason=nosql_injection_or_schema_violation  "
            "field=%s  code=%s  peer=%s  payload_keys=%s",
            field, code, req.remote_addr, list(raw.keys()),
        )
        return None, (jsonify({
            "error": "schema_violation",
            "field": field,
            "code": code,
        }), 400)

    logger.info("ALLOW  patient_id=%s  ts=%d  hr=%.1f",
                record.patient_id, record.timestamp, record.heart_rate)
    return record.model_dump(), None


# ---------------------------------------------------------------------------
# Standalone demo — run `python cloud_schema.py` to reproduce report figures
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Mini demo without spinning up a Flask app — prints 4 decisions that
    # correspond 1:1 to the screenshots needed for CW2 Page 3.
    from pydantic import BaseModel as _BM  # noqa

    print("=" * 70)
    print("Pydantic schema defence — demo")
    print("=" * 70)

    cases = [
        ("BENIGN",
         {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": 78.5}),
        ("INJECT-1  operator in id",
         {"patient_id": {"$ne": None}, "timestamp": 1713355200, "heart_rate": 70.0}),
        ("INJECT-2  operator in hr",
         {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": {"$gt": 0}}),
        ("COERCION  string number",
         {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": "78"}),
        ("EXTRA      smuggled $where",
         {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": 78.0,
          "$where": "sleep(5000)"}),
        ("OUT-OF-RANGE heart_rate",
         {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": 9999.0}),
    ]

    for label, payload in cases:
        try:
            HeartRateRecord(**payload)
            print(f"  [ALLOW] {label:<30}  payload={payload}")
        except ValidationError as e:
            first = e.errors()[0]
            print(f"  [BLOCK] {label:<30}  field={'.'.join(str(x) for x in first['loc'])}  "
                  f"code={first['type']}")
    print()

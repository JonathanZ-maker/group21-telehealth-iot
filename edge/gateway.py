"""
edge/gateway.py
Gateway service for the Group 21 telehealth IoT pipeline.

Responsibilities
----------------
1. Verify wearable packets with HMAC-SHA256.
2. Reject stale or replayed packets.
3. Run ZYM's AI-IDS and differential-privacy hooks.
4. Forward accepted packets to the cloud API with a gateway-scoped JWT.
5. Demonstrate resilient security via manual key rotation.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from collections import deque
from pathlib import Path
from statistics import median

import numpy as np
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zym_defense.gateway_ai_ids import AIIDS, WINDOW, get_detector  # noqa: E402
from zym_defense.gateway_dp import privatise_heart_rate  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv(ROOT / ".env")

LISTEN_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
CLOUD_BASE_URL = os.environ.get("CLOUD_URL", "http://127.0.0.1:5000").rstrip("/")
DEVICE_ID = os.environ.get("GATEWAY_DEVICE_ID", "gateway-edge-01")

NONCE_TTL_SECONDS = int(os.environ.get("GATEWAY_NONCE_TTL", "300"))
FRESHNESS_WINDOW_SECONDS = int(os.environ.get("GATEWAY_FRESHNESS_WINDOW", "60"))
KEY_GRACE_SECONDS = int(os.environ.get("GATEWAY_KEY_GRACE_SECONDS", "300"))
PATIENT_WINDOW = int(os.environ.get("GATEWAY_PATIENT_WINDOW", "30"))

DATASET_PATH = ROOT / "data" / "processed" / "heart_rate_cleaned.csv"

_secret_env = os.environ.get("HMAC_DEVICE_SECRET")
if not _secret_env:
    raise RuntimeError(
        "HMAC_DEVICE_SECRET not set. Copy .env.example to .env and provide a secret."
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [GATEWAY] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("edge.gateway")


# ---------------------------------------------------------------------------
# App + mutable process state
# ---------------------------------------------------------------------------
app = Flask(__name__)
http = requests.Session()

CURRENT_SECRET = _secret_env.encode("utf-8")
PREVIOUS_SECRET: bytes | None = None
PREVIOUS_SECRET_EXPIRES_AT = 0.0

SEEN_NONCES: dict[str, float] = {}
PATIENT_HISTORY: dict[str, deque[float]] = {}

CLOUD_TOKEN: str | None = None


# ---------------------------------------------------------------------------
# Helpers: HMAC / replay / stale
# ---------------------------------------------------------------------------
def _canonical_blob(packet: dict) -> bytes:
    return json.dumps(
        {k: packet[k] for k in ("patient_id", "timestamp", "heart_rate", "nonce")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _required_fields_present(packet: dict) -> bool:
    required = {"patient_id", "timestamp", "heart_rate", "nonce", "hmac_sig"}
    return isinstance(packet, dict) and required.issubset(packet)


def _prune_seen_nonces(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired = [nonce for nonce, seen_at in SEEN_NONCES.items() if now - seen_at > NONCE_TTL_SECONDS]
    for nonce in expired:
        SEEN_NONCES.pop(nonce, None)


def _active_secrets(now: float | None = None) -> list[bytes]:
    now = time.time() if now is None else now
    active = [CURRENT_SECRET]
    if PREVIOUS_SECRET is not None and now <= PREVIOUS_SECRET_EXPIRES_AT:
        active.append(PREVIOUS_SECRET)
    return active


def verify_hmac(packet: dict) -> bool:
    if not _required_fields_present(packet):
        return False
    try:
        supplied = str(packet["hmac_sig"])
        blob = _canonical_blob(packet)
    except (KeyError, TypeError, ValueError):
        return False

    for secret in _active_secrets():
        expected = hmac.new(secret, blob, hashlib.sha256).hexdigest()
        if hmac.compare_digest(supplied, expected):
            return True
    return False


def is_stale(packet: dict) -> bool:
    try:
        ts = int(packet["timestamp"])
    except (KeyError, TypeError, ValueError):
        return True
    return abs(int(time.time()) - ts) > FRESHNESS_WINDOW_SECONDS


def is_replay(packet: dict) -> bool:
    nonce = str(packet.get("nonce", ""))
    now = time.time()
    _prune_seen_nonces(now)
    if nonce in SEEN_NONCES:
        return True
    SEEN_NONCES[nonce] = now
    return False


# ---------------------------------------------------------------------------
# Helpers: patient history + AI-IDS
# ---------------------------------------------------------------------------
def _patient_buffer(patient_id: str) -> deque[float]:
    buf = PATIENT_HISTORY.get(patient_id)
    if buf is None:
        buf = deque(maxlen=PATIENT_WINDOW)
        PATIENT_HISTORY[patient_id] = buf
    return buf


def patient_reference(patient_id: str) -> float | None:
    buf = PATIENT_HISTORY.get(patient_id)
    return float(median(buf)) if buf else None


def remember_patient_value(patient_id: str, heart_rate: float) -> None:
    _patient_buffer(patient_id).append(float(heart_rate))


def _load_training_series() -> np.ndarray:
    values: list[float] = []
    if DATASET_PATH.exists():
        with open(DATASET_PATH, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    values.append(float(row["heart_rate"]))
                except (KeyError, TypeError, ValueError):
                    continue
    if len(values) >= WINDOW:
        return np.asarray(values, dtype=np.float32)

    log.warning(
        "AI-IDS fallback dataset unavailable or too small at %s; using synthetic healthy baseline.",
        DATASET_PATH,
    )
    rng = np.random.default_rng(42)
    synthetic = rng.normal(loc=75.0, scale=6.0, size=5000).clip(50, 110)
    return synthetic.astype(np.float32)


def _load_ai_ids() -> AIIDS:
    try:
        detector = get_detector()
        log.info("AI-IDS model loaded from zym_defense/models/iforest.pkl")
        return detector
    except Exception as exc:  # noqa: BLE001 - gateway-level fallback is intentional
        log.warning("AI-IDS pretrained model unavailable (%s). Training a local fallback model.", exc)
        detector = AIIDS(contamination=0.01, random_state=0)
        detector.fit(_load_training_series())
        return detector


AI_IDS = _load_ai_ids()


# ---------------------------------------------------------------------------
# Helpers: cloud forwarding
# ---------------------------------------------------------------------------
def _cloud_url(path: str) -> str:
    return f"{CLOUD_BASE_URL}{path}"


def _enroll_gateway() -> str:
    response = http.post(
        _cloud_url("/enroll"),
        json={"device_id": DEVICE_ID},
        timeout=3.0,
    )
    response.raise_for_status()
    body = response.json()
    token = body.get("token")
    if not token:
        raise RuntimeError("cloud /enroll returned no token")
    log.info("Obtained cloud token for device=%s", DEVICE_ID)
    return str(token)


def _get_cloud_token(force_refresh: bool = False) -> str:
    global CLOUD_TOKEN
    if force_refresh or not CLOUD_TOKEN:
        CLOUD_TOKEN = _enroll_gateway()
    return CLOUD_TOKEN


def forward_to_cloud(packet: dict) -> requests.Response:
    token = _get_cloud_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = http.post(_cloud_url("/ingest"), json=packet, headers=headers, timeout=4.0)

    if response.status_code == 401:
        log.warning("Cloud rejected cached token; refreshing gateway token and retrying once.")
        token = _get_cloud_token(force_refresh=True)
        headers = {"Authorization": f"Bearer {token}"}
        response = http.post(_cloud_url("/ingest"), json=packet, headers=headers, timeout=4.0)

    response.raise_for_status()
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/upload")
def upload():
    packet = request.get_json(silent=True)
    if not isinstance(packet, dict):
        log.warning("BLOCK  reason=invalid_payload  peer=%s", request.remote_addr)
        return jsonify({"error": "invalid_payload"}), 400

    if not verify_hmac(packet):
        log.warning(
            "BLOCK  reason=hmac_failed  patient_id=%s  peer=%s",
            packet.get("patient_id", "?"),
            request.remote_addr,
        )
        return jsonify({"error": "hmac_failed"}), 401

    if is_stale(packet):
        log.warning(
            "BLOCK  reason=stale  patient_id=%s  ts=%s",
            packet.get("patient_id", "?"),
            packet.get("timestamp"),
        )
        return jsonify({"error": "stale"}), 401

    if is_replay(packet):
        log.warning(
            "BLOCK  reason=replay  patient_id=%s  nonce=%s",
            packet.get("patient_id", "?"),
            packet.get("nonce"),
        )
        return jsonify({"error": "replay"}), 401

    patient_id = str(packet["patient_id"])
    heart_rate = float(packet["heart_rate"])

    flagged, score = AI_IDS.inspect(patient_id, heart_rate)  # [ZYM]
    if flagged:
        rounded_score = round(score, 4) if score != float("inf") else score
        log.warning(
            "BLOCK  reason=anomaly  patient_id=%s  hr=%.2f  score=%s",
            patient_id,
            heart_rate,
            rounded_score,
        )
        return jsonify({"error": "anomaly", "score": rounded_score}), 400

    reference = patient_reference(patient_id)
    packet["heart_rate"] = round(  # [ZYM]
        privatise_heart_rate(heart_rate, reference=reference),
        2,
    )
    remember_patient_value(patient_id, heart_rate)

    try:
        downstream = forward_to_cloud(packet)
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = getattr(getattr(exc, "response", None), "text", "")
        log.error(
            "FORWARD_FAIL  patient_id=%s  downstream_status=%s  error=%s  body=%s",
            patient_id,
            status,
            exc,
            body[:200],
        )
        return jsonify({"error": "cloud_forward_failed", "downstream_status": status}), 502

    log.info(
        "ALLOW  patient_id=%s  raw_hr=%.2f  dp_hr=%.2f  cloud_status=%d",
        patient_id,
        heart_rate,
        float(packet["heart_rate"]),
        downstream.status_code,
    )
    return jsonify({"status": "ok"}), 200


@app.post("/rotate")
def rotate():
    global CURRENT_SECRET, PREVIOUS_SECRET, PREVIOUS_SECRET_EXPIRES_AT

    body = request.get_json(silent=True) or {}
    provided = body.get("new_secret")
    new_secret = (
        str(provided).encode("utf-8")
        if provided
        else secrets.token_urlsafe(32).encode("utf-8")
    )

    PREVIOUS_SECRET = CURRENT_SECRET
    PREVIOUS_SECRET_EXPIRES_AT = time.time() + KEY_GRACE_SECONDS
    CURRENT_SECRET = new_secret

    log.warning(
        "ROTATE  grace_seconds=%d  previous_key_valid_until=%d",
        KEY_GRACE_SECONDS,
        int(PREVIOUS_SECRET_EXPIRES_AT),
    )
    return jsonify(
        {
            "status": "rotated",
            "grace_seconds": KEY_GRACE_SECONDS,
            "previous_key_valid_until": int(PREVIOUS_SECRET_EXPIRES_AT),
        }
    ), 200


@app.get("/health")
def health():
    previous_active = PREVIOUS_SECRET is not None and time.time() <= PREVIOUS_SECRET_EXPIRES_AT
    return jsonify(
        {
            "status": "ok",
            "cloud_url": CLOUD_BASE_URL,
            "cached_nonces": len(SEEN_NONCES),
            "tracked_patients": len(PATIENT_HISTORY),
            "previous_key_active": previous_active,
        }
    ), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting gateway.py on %s:%d -> cloud=%s", LISTEN_HOST, LISTEN_PORT, CLOUD_BASE_URL)
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, debug=False)

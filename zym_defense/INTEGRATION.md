# `zym_defense/` — Integration Guide for Group 21

**Author:** ZYM  
**Audience:** LYZ (edge gateway owner), YYX (cloud API owner), LKK (data & attack owner)  
**Purpose:** Explain how the four defence modules in this directory plug into the
gateway and cloud services with minimal changes to your code.

---

## 1. What this directory provides

| File | Layer | What it defends | One-sentence API |
|------|-------|-----------------|------------------|
| `gateway_ai_ids.py` | Edge | Semantic anomalies in heart-rate values (e.g. spoofed 300 BPM, dead-stick) | `flagged, score = get_detector().inspect(device_id, hr)` |
| `gateway_dp.py`     | Edge | Per-record privacy leakage to the cloud / downstream consumers            | `noisy_hr = privatise_heart_rate(hr, reference=recent_median)` |
| `cloud_schema.py`   | Cloud | NoSQL injection via operator-embedded JSON payloads                      | `record, err = validate_payload(request)` |
| `cloud_auth.py`     | Cloud | Unauthorised / over-scoped database access                               | `@require_jwt("ingest:write")` decorator |

**Design contract:** every module is *stateless from the caller's point of view*,
pure Python, and never modifies your files. You import, call, done.

---

## 2. How to wire them in

### 2.1 `gateway.py` (LYZ)

The full request path on the gateway becomes:

```
BLE packet → HMAC verify (yours) → AI-IDS inspect → DP privatise → POST to cloud
```

**Concrete integration** (add to your existing `gateway.py`):

```python
# --- imports at top of file -------------------------------------------------
from zym_defense.gateway_ai_ids import get_detector
from zym_defense.gateway_dp     import privatise_heart_rate

# Load the trained model once, at process start (not per-request):
AI_IDS = get_detector()   # reads zym_defense/models/iforest.pkl

# --- inside your existing handler, AFTER your HMAC check passes -------------
@app.route("/upload", methods=["POST"])
def upload():
    packet = request.get_json()

    # [LYZ] 1. HMAC integrity check — your existing code
    if not verify_hmac(packet):
        return {"error": "hmac_failed"}, 401

    # [ZYM] 2. AI-IDS semantic anomaly check
    flagged, score = AI_IDS.inspect(packet["patient_id"], packet["heart_rate"])
    if flagged:
        # Drop + log. Do NOT forward to cloud.
        return {"error": "anomaly_detected", "score": round(score, 4)}, 400

    # [ZYM] 3. Differential privacy — perturb the value before upload
    #         `reference` is optional; pass the patient's recent median if
    #         you're tracking one, otherwise the engine falls back to a
    #         safe default.
    packet["heart_rate"] = privatise_heart_rate(
        packet["heart_rate"],
        reference=patient_medians.get(packet["patient_id"]),
    )

    # [LYZ] 4. Forward to cloud — your existing code
    forward_to_cloud(packet)
    return {"status": "ok"}, 200
```

**Total changes to your file:** 2 imports, 1 module-level variable, ~6 lines in
the handler. Nothing else.

---

### 2.2 `cloud.py` (YYX)

The cloud request path becomes:

```
HTTP request → JWT verify → Pydantic schema validate → MongoDB insert
```

**Concrete integration** (add to your existing `cloud.py`):

```python
# --- imports at top of file -------------------------------------------------
from zym_defense.cloud_auth   import require_jwt, issue_token  # issue_token for /login
from zym_defense.cloud_schema import validate_payload

# --- protected ingest endpoint ----------------------------------------------
@app.route("/ingest", methods=["POST"])
@require_jwt("ingest:write")                         # [ZYM] zero-trust check
def ingest():
    record, err = validate_payload(request)           # [ZYM] injection guard
    if err:
        return err                                    # 400 with reason code

    # [YYX] Your existing MongoDB insert:
    db.readings.insert_one(record)
    return {"status": "stored"}, 200


# --- read endpoint requires a different scope --------------------------------
@app.route("/readings", methods=["GET"])
@require_jwt("readings:read")
def list_readings():
    # [YYX] Your existing query code:
    cursor = db.readings.find(limit=100)
    return {"records": list(cursor)}, 200


# --- enrolment endpoint (unauthenticated by design) --------------------------
@app.route("/enroll", methods=["POST"])
def enroll():
    """
    Mint a device token. In a real deployment this would itself be protected
    by a provisioning secret; kept open here for the prototype demo.
    """
    body = request.get_json() or {}
    device_id = body.get("device_id", "unknown")
    token = issue_token(device_id, ["ingest:write"])
    return {"token": token}, 200
```

**Total changes to your file:** 2 imports, 1 decorator per route, 1 one-liner
validation call per route.

---

## 3. Attack test vectors (for red-team scripts)

Use these payloads to verify the defences fire correctly. Every one of them
will be **blocked** once integration is done.

### Against `/ingest` (requires JWT + schema checks)

```python
import requests

BASE = "http://localhost:5000"
token = requests.post(f"{BASE}/enroll", json={"device_id": "dev-01"}).json()["token"]
H = {"Authorization": f"Bearer {token}"}

# 1. No token → 401 (cloud_auth.py)
requests.post(f"{BASE}/ingest", json={"patient_id": "P1", "timestamp": 1, "heart_rate": 75.0})

# 2. Tampered token → 401 (cloud_auth.py)
requests.post(f"{BASE}/ingest",
              headers={"Authorization": "Bearer AAAA.BBBB.CCCC"},
              json={"patient_id": "P1", "timestamp": 1, "heart_rate": 75.0})

# 3. NoSQL injection → 400 (cloud_schema.py)
requests.post(f"{BASE}/ingest", headers=H,
              json={"patient_id": {"$ne": None}, "timestamp": 1, "heart_rate": 75.0})

# 4. Smuggled $where operator → 400 (cloud_schema.py)
requests.post(f"{BASE}/ingest", headers=H,
              json={"patient_id": "P1", "timestamp": 1, "heart_rate": 75.0,
                    "$where": "sleep(5000)"})

# 5. Scope mismatch — ingest token trying to read → 401 (cloud_auth.py)
requests.get(f"{BASE}/readings", headers=H)

# 6. Out-of-range value → 400 (cloud_schema.py)
requests.post(f"{BASE}/ingest", headers=H,
              json={"patient_id": "P1", "timestamp": 1, "heart_rate": 9999.0})
```

### Against the gateway (AI-IDS)

Pipe a malicious stream into `/upload` and you should see the gateway log
`ALERT` lines and return `400 anomaly_detected`:

```python
# Spike attack — HMAC-valid packet with a spoofed extreme heart rate
for hr in [75, 73, 74, 76, 72, 75, 74, 75, 76, 73,  # warmup (10 benign)
           275, 260, 280]:                           # injection
    packet = build_signed_packet("P1", hr)           # LYZ's HMAC helper
    requests.post("http://localhost:8000/upload", json=packet)
```

---

## 4. Data contract (what I expect from the pipeline)

All four modules assume records in this shape (as produced by `wearable.py`):

```json
{
  "patient_id": "P001",        // string, 1–64 chars, no '$' prefix
  "timestamp": 1713355200,     // int, unix seconds
  "heart_rate": 78.5,          // float, 20.0 – 250.0 (physiological plausibility)
  "nonce":      "a3f7...",     // optional, string ≤128 chars — added by LYZ for replay
  "hmac_sig":   "c91e..."      // optional, string ≤128 chars — added by LYZ
}
```

If the wearable sim produces anything else (e.g. `heart_rate` as a string),
tell me and I'll relax the schema.

---

## 5. Running the unit demos

Each module has a `__main__` block that produces the screenshots needed for
the CW2 report. They require no external services:

```bash
cd zym_defense
python cloud_schema.py       # shows 6 allow/block decisions
python cloud_auth.py         # shows JWT allow + 5 block scenarios
python gateway_dp.py         # shows DP MAE at ε ∈ {0.1, 0.5, 1.0, 5.0}
python gateway_ai_ids.py     # trains a demo model and probes 4 attacks
```

Outputs are both printed to stdout and logged via the `zym.*` loggers, so
terminal screenshots work directly.

---

## 6. Dependencies (add to your `requirements.txt`)

```
pydantic>=2.5
PyJWT>=2.7
numpy>=1.24
scikit-learn>=1.3
flask>=3.0
```

---

## 7. If anything breaks

Ping me first before changing anything under `zym_defense/`. The modules are
designed to be modified in isolation so that my individual contribution stays
clearly delineated for the IPAC evaluation. Thanks!

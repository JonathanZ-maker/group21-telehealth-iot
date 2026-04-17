# Edge Gateway + HMAC Defence — Tasks for LYZ

**Folder:** `edge/` (file `gateway.py`)  
**Owner:** LYZ  
**Complements:**  
- LKK's `edge/wearable.py` (upstream)  
- YYX's `cloud/cloud.py` (downstream)  
- ZYM's `zym_defense/` (plug-in modules — see [`zym_defense/INTEGRATION.md`](../zym_defense/INTEGRATION.md))

---

## 🎯 What you need to deliver

1. A Flask (or FastAPI) service `edge/gateway.py` listening on port 8000
2. HMAC verification that rejects tampered and replayed packets
3. Device-key rotation logic (the "resilient security" requirement)
4. Wiring hooks for ZYM's AI-IDS + DP modules — **2 imports + ~6 lines of code**, pattern given below
5. Forward accepted packets to YYX's cloud API

---

## 📐 High-level request path

```
POST /upload  →  [LYZ] HMAC verify  →  [LYZ] nonce-replay check
              →  [ZYM] AI-IDS inspect
              →  [ZYM] DP privatise
              →  [LYZ] POST to cloud
              →  return 200
```

---

## 🔐 HMAC defence — design decisions to commit to

1. **Algorithm**: HMAC-SHA256 (128-bit collision resistance is overkill but simple)
2. **Canonicalisation**: agree with LKK that the signed blob is
   ```python
   json.dumps({k: p[k] for k in ("patient_id","timestamp","heart_rate","nonce")},
              sort_keys=True, separators=(",", ":")).encode()
   ```
3. **Replay defence**: maintain an in-memory set of seen nonces for the last 5 minutes, reject duplicates.  Add a timestamp freshness check too (reject packets with `|now - timestamp| > 60 s`).
4. **Key rotation** (resilient-security hook): every N hours rotate to a new key, keep a short grace-window where both keys are valid. For the prototype a manual `/rotate` admin endpoint is fine — you just need to demonstrate the mechanism.

---

## 🧩 Hooking ZYM's modules (2 imports + ~6 lines)

Full spec: [`zym_defense/INTEGRATION.md`](../zym_defense/INTEGRATION.md).

Short version — paste the bracketed sections into your handler after your HMAC check passes:

```python
from zym_defense.gateway_ai_ids import get_detector
from zym_defense.gateway_dp     import privatise_heart_rate

AI_IDS = get_detector()   # load once at startup

@app.route("/upload", methods=["POST"])
def upload():
    packet = request.get_json()

    if not verify_hmac(packet):                                # [LYZ]
        return {"error": "hmac_failed"}, 401
    if is_replay(packet):                                      # [LYZ]
        return {"error": "replay"}, 401

    flagged, score = AI_IDS.inspect(packet["patient_id"],      # [ZYM]
                                    packet["heart_rate"])
    if flagged:
        return {"error": "anomaly", "score": round(score, 4)}, 400

    packet["heart_rate"] = privatise_heart_rate(               # [ZYM]
        packet["heart_rate"],
        reference=patient_medians.get(packet["patient_id"]),
    )

    forward_to_cloud(packet)                                   # [LYZ]
    return {"status": "ok"}, 200
```

---

## 📤 Forwarding to the cloud

The cloud API requires a JWT (ZYM's module). You have two deployment choices:

- **Gateway-as-service-account** (recommended): the gateway holds its own long-lived service token with scope `ingest:write`. On startup call `POST {CLOUD_URL}/enroll` once with your device_id, cache the token, refresh it before expiry. Simpler.
- **Per-packet token passthrough**: each wearable also has a JWT and the gateway relays it. Closer to "true zero-trust" but more moving parts.

Recommendation: go with the first. The report can note this as a deliberate trade-off.

---

## 📸 Artifacts to capture

- [ ] Screenshot: gateway refusing a tampered packet with `401 hmac_failed`
- [ ] Screenshot: gateway refusing a replayed packet with `401 replay`
- [ ] Screenshot: the key-rotation log line
- [ ] A flow diagram of the gateway pipeline for CW2 Page 1

---

## ✅ Done when

- [ ] `edge/gateway.py` runs and LKK's wearable successfully uploads
- [ ] Tampered / replayed packets are rejected with the right HTTP codes
- [ ] ZYM's two hooks are in place and commented with `# [ZYM]` tags (so IPAC blame is clear)
- [ ] A manual `/rotate` endpoint works
- [ ] All `logger` output is screenshot-friendly (red for blocks)

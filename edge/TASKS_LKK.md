# Wearable Simulator — Tasks for LKK

**Folder:** `edge/` (file `wearable.py`)  
**Owner:** LKK  
**Complements:** LYZ's `gateway.py` in the same folder

---

## 🎯 What you need to deliver

A Python script `edge/wearable.py` that:

1. Reads `data/processed/heart_rate_cleaned.csv` row-by-row
2. For each row, builds a JSON packet matching the **data contract**
3. Signs it with HMAC (shared key loaded from `.env` — LYZ defines the key scheme)
4. POSTs it to the gateway at `$GATEWAY_URL` (default `http://127.0.0.1:8000/upload`)
5. Sleeps 1 second between packets to simulate BLE 1 Hz telemetry

---

## 📦 The JSON packet you must produce

```json
{
  "patient_id": "P001",
  "timestamp":  1713355200,
  "heart_rate": 78.5,
  "nonce":      "<random 16-byte hex>",
  "hmac_sig":   "<HMAC-SHA256 of the other four fields>"
}
```

See [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md) for the authoritative spec.

---

## 🔐 How to compute the HMAC (coordinate with LYZ)

LYZ will finalise the exact canonicalisation, but as a starting point:

```python
import hmac, hashlib, json, os, secrets

SECRET = os.environ["HMAC_DEVICE_SECRET"].encode()

def sign(payload: dict) -> dict:
    payload["nonce"] = secrets.token_hex(16)
    # Canonicalise by sorting keys, no spaces — identical on both ends
    to_sign = json.dumps({k: payload[k] for k in
                          ("patient_id", "timestamp", "heart_rate", "nonce")},
                         sort_keys=True, separators=(",", ":")).encode()
    payload["hmac_sig"] = hmac.new(SECRET, to_sign, hashlib.sha256).hexdigest()
    return payload
```

**Important:** agree with LYZ on the exact `to_sign` format, or signatures won't match.

---

## 🏃 Operational behaviour

- Default loop: infinite replay of the CSV
- `--speed N` flag to send at N × realtime (for demos / experiments)
- `--patient <id>` flag to stream only one patient (useful for attack reproduction)
- On network error, retry up to 3 times with 2 s backoff, then skip the packet and log
- Log every sent packet to stdout in a compact one-line format:
  `[send] P001 ts=1713355200 hr=78.5`

---

## 🧪 Acceptance test

After LYZ's gateway is up:

```bash
python edge/wearable.py --speed 10
```

You should see the gateway log `OK` responses at ~10 Hz.

---

## ✅ Done when

- [ ] `edge/wearable.py` exists and runs
- [ ] HMAC signature agrees with LYZ's `gateway.py` verifier
- [ ] Handles CSV not found / network down gracefully
- [ ] Terminal output is screenshot-ready for the demo video

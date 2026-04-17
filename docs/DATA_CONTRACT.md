# Data Contract — Group 21 Telehealth Pipeline

**Status:** v1.0 — agreed by all members  
**Owner:** updates must be proposed via PR and signed off by every member  
**Scope:** every JSON packet that crosses a service boundary in this system

---

## The canonical packet

```json
{
  "patient_id": "P001",
  "timestamp":  1713355200,
  "heart_rate": 78.5,
  "nonce":      "a3f7c1b2d4e5f6a7",
  "hmac_sig":   "c91ebd7a1f2b3c4d..."
}
```

## Field-by-field spec

| Field | Type | Constraints | Set by | Read by |
|-------|------|-------------|--------|---------|
| `patient_id` | JSON string | 1–64 chars, no leading `$`, no whitespace | LKK (`wearable.py`) | LYZ, ZYM, YYX |
| `timestamp` | JSON integer | `≥ 0`, unix seconds, `|now − ts| ≤ 60 s` at gateway | LKK | LYZ (freshness), YYX (store) |
| `heart_rate` | JSON number (float) | `20.0 ≤ hr ≤ 250.0` | LKK | LYZ (HMAC covers), ZYM (AI-IDS + DP), YYX (store) |
| `nonce` | JSON string | 16 hex chars (64 bits), fresh per packet | LKK | LYZ (replay cache) |
| `hmac_sig` | JSON string | 64 hex chars (HMAC-SHA256 hex) | LKK | LYZ (verify) |

After DP on the gateway, the outbound `heart_rate` becomes a noisy float. All other fields pass through unchanged.

---

## Canonical signing blob (HMAC)

Both sides must serialise identically:

```python
import json
to_sign = json.dumps(
    {k: packet[k] for k in ("patient_id", "timestamp", "heart_rate", "nonce")},
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
hmac_sig = hmac.new(SECRET_KEY, to_sign, hashlib.sha256).hexdigest()
```

Rules:
- Keys sorted alphabetically
- `separators=(",", ":")` — no spaces
- UTF-8 bytes
- The signature itself (`hmac_sig`) and `timestamp` are **not** re-signed recursively — only the four data fields are signed

---

## Rejection codes (shared across services)

| Code | HTTP | Reason | Who emits |
|------|------|--------|-----------|
| `hmac_failed` | 401 | HMAC signature invalid | LYZ gateway |
| `replay` | 401 | Nonce seen recently | LYZ gateway |
| `stale` | 401 | Timestamp outside freshness window | LYZ gateway |
| `anomaly` | 400 | AI-IDS flagged the value | ZYM / LYZ gateway |
| `unauthorized` | 401 | JWT missing / expired / tampered / revoked | ZYM cloud |
| `forbidden_scope` | 401 | JWT scope insufficient | ZYM cloud |
| `schema_violation` | 400 | Payload fails Pydantic validation | ZYM cloud |

Attack scripts test for these exact codes.

---

## Versioning

If anyone needs to add a field (e.g. `device_id`, `battery_level`):

1. Open an issue tagged `data-contract`
2. Propose a PR updating **this file first**
3. Bump the contract version in the top matter
4. Every service owner acknowledges in the PR thread before merge

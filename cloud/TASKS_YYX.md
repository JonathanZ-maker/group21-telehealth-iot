# Cloud API + MongoDB — Tasks for YYX

**Folder:** `cloud/` (file `cloud.py`)  
**Owner:** YYX  
**Complements:**  
- LYZ's `edge/gateway.py` (upstream client)  
- ZYM's `zym_defense/cloud_schema.py` + `cloud_auth.py` (inline middleware — see [`zym_defense/INTEGRATION.md`](../zym_defense/INTEGRATION.md))  
- Your own `attack/attack2_nosql.py`

---

## 🎯 What you need to deliver

1. A Flask service `cloud/cloud.py` listening on port 5000
2. MongoDB Atlas connection (free tier is fine) — share the URI with the team **via the private chat only**, not in the repo
3. Three routes, all protected by ZYM's middleware:
   - `POST /ingest` — gateway sends one heart-rate packet
   - `GET /readings` — clinician-style read endpoint (target for Attack 2)
   - `POST /enroll` — mint a device JWT (left unauthenticated by design)
4. Data-rollback utility (the "resilient security" requirement — if anomalies are detected the cloud can revert)

---

## 📐 High-level request path

```
POST /ingest  →  [ZYM] @require_jwt("ingest:write")
              →  [ZYM] validate_payload(request)
              →  [YYX] db.readings.insert_one(record)
              →  return 200
```

---

## 🧩 Hooking ZYM's modules

Full spec: [`zym_defense/INTEGRATION.md`](../zym_defense/INTEGRATION.md).

Short version — your entire route looks like this:

```python
from flask import Flask, request
from pymongo import MongoClient
import os

from zym_defense.cloud_auth   import require_jwt, issue_token
from zym_defense.cloud_schema import validate_payload

app = Flask(__name__)
db = MongoClient(os.environ["MONGO_URI"]).telehealth

@app.post("/ingest")
@require_jwt("ingest:write")                            # [ZYM] JWT gate
def ingest():
    record, err = validate_payload(request)              # [ZYM] schema gate
    if err:
        return err                                       # 400 with reason
    db.readings.insert_one(record)                       # [YYX]
    return {"status": "stored"}, 200

@app.get("/readings")
@require_jwt("readings:read")                            # [ZYM] different scope
def readings():
    cur = db.readings.find({}, {"_id": 0}).limit(100)    # [YYX]
    return {"records": list(cur)}, 200

@app.post("/enroll")
def enroll():
    body = request.get_json() or {}
    token = issue_token(body.get("device_id", "unknown"),
                        ["ingest:write"])
    return {"token": token}, 200
```

---

## 🔄 Data rollback (resilient security)

Requirement: when a downstream process flags an ingestion run as poisoned, the cloud can restore to a known-good state.

Simplest acceptable implementation:

- Add a `_ingested_at` timestamp to every stored record
- Provide a small admin function: `rollback(since_ts)` that deletes all records with `_ingested_at >= since_ts`
- Demonstrate it once in the video — "at 14:05 the anomaly detector flagged device P003; operator rolls back to 14:00; DB is clean"

This alone satisfies the "弹性安全 / resilience" row in the defence architecture.

---

## 📸 Artifacts to capture

- [ ] Screenshot: successful `/ingest` with 200
- [ ] Screenshot: unauthenticated `/ingest` returning 401 (ZYM's JWT)
- [ ] Screenshot: `/ingest` with NoSQL operator returning 400 (ZYM's schema)
- [ ] Screenshot: MongoDB Atlas showing stored records
- [ ] Screenshot: rollback in action

---

## ✅ Done when

- [ ] `cloud/cloud.py` runs against real MongoDB Atlas
- [ ] LYZ's gateway can post with a valid JWT
- [ ] Your own `attack/attack2_nosql.py` fully fails against this hardened API
- [ ] Rollback demonstrated
- [ ] `.env.example` reflects any new env vars you introduced

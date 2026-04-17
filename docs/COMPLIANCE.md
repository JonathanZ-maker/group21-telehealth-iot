# Compliance Mapping — GDPR / EU CRA / UK PSTI

**Used by:** CW2 Page 5  
**Authors:** ZYM + LYZ jointly  
**Evidence pointer:** every row cites the code file that implements the control

---

## 1. GDPR (Regulation 2016/679)

| Article | Requirement | How we meet it | Evidence |
|---------|-------------|----------------|----------|
| Art. 5(1)(c) | Data minimisation | Only `patient_id`, `timestamp`, `heart_rate` are collected; Pydantic's `extra="forbid"` rejects smuggled fields | `zym_defense/cloud_schema.py` |
| Art. 5(1)(f) | Integrity & confidentiality | HMAC on BLE link + HTTPS on cloud link + JWT-enforced access + DP on outbound readings | `edge/gateway.py`, `zym_defense/cloud_auth.py`, `zym_defense/gateway_dp.py` |
| Art. 25 | Data protection by design | Schema, authZ, and DP are applied at ingress, not bolted on at export | all four ZYM modules |
| Art. 32 | Security of processing | Pseudonymisation (DP), encryption in transit (TLS), integrity checks (HMAC + JWT signatures), resilience (key rotation, rollback) | whole defence stack |
| Art. 33 | Breach notification | Not implementation-level; documented in report | report §5.2 |
| Art. 9 | Processing of special category (health) data | Explicit lawful basis documented in report; noise-protected release for analytics | report §5.1 |

## 2. EU Cyber Resilience Act (CRA)

| Annex I provision | Requirement | How we meet it | Evidence |
|-------------------|-------------|----------------|----------|
| §1(3)(a) | Protect from unauthorised access | JWT scope enforcement, HMAC-authenticated link | `cloud_auth.py`, gateway HMAC |
| §1(3)(b) | Confidentiality of stored / transmitted data | HTTPS in transit, DP on outbound analytics | `gateway_dp.py`, gateway TLS config |
| §1(3)(d) | Process only necessary data | Pydantic schema enforces the minimal field set | `cloud_schema.py` |
| §1(3)(e) | Protect integrity of data | HMAC integrity check; AI-IDS semantic check | gateway HMAC, `gateway_ai_ids.py` |
| §1(3)(h) | Resilience against DoS — **limited in our prototype** | Nonce cache + replay reject mitigates basic flood; discussed as limitation | gateway replay check |
| §1(3)(j) | Secure default configuration | Secrets read from env, no hard-coded keys; `.env` gitignored | `.env.example`, `.gitignore` |
| Art. 13 | Vulnerability handling process | Group's issue tracker on GitHub | repository `issues` tab |

## 3. UK Product Security and Telecommunications Infrastructure Act (PSTI)

| PSTI regulation requirement | How we meet it | Evidence |
|-----------------------------|----------------|----------|
| Ban on universal default passwords | No default passwords; device credentials are per-device HMAC keys provisioned out-of-band | `.env.example` has only placeholders |
| Requirement to publish how to report security issues | `SECURITY.md` in repo root (to add in final submission) | `SECURITY.md` |
| Transparent minimum security update period | Documented in README submission notes | README |

---

## 4. Ethical considerations (CW2 explicit requirement)

- **Surveillance risk:** the AI-IDS (`gateway_ai_ids.py`) only inspects heart-rate statistics, not behavioural content; it runs at the edge so raw readings do not leave the gateway for analysis. This keeps monitoring within the purpose stated to the patient.
- **User consent:** because we add calibrated noise at the gateway (`gateway_dp.py`), individual-level analytics downstream cannot re-identify patients from the cloud store alone; this is consistent with an informed-consent scheme limited to aggregate public-health statistics.
- **Explainability:** Isolation-Forest decisions are logged with the feature window that triggered them, making a human review of flagged events tractable.
- **Fairness:** we acknowledge that the training distribution (open heart-rate datasets) may under-represent specific populations (pregnancy, paediatric, athletic). The report's Limitations section flags this as the main ethical risk of the AI component.

---

## 5. Residual risks and limitations (for honest reporting)

- DP parameter ε = 1.0 per release with no global composition tracker — long-lived users see their cumulative privacy loss grow
- Symmetric HS256 JWT — suitable for a single-tenant prototype, not for a multi-hospital deployment
- No rate limiting on `/enroll` or `/ingest` — DoS out of scope
- MongoDB Atlas trusted as a black box — we rely on its own attestations

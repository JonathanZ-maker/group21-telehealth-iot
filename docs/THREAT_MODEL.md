# Threat Model — Group 21 Telehealth IoT System

**Used by:** CW1 Page 2  
**Methodology:** STRIDE-style enumeration, narrowed to two focal threats per the assignment's minimum requirement

---

## System under analysis

A three-tier connected-healthcare wearable system deployed in the EU for remote patient monitoring, subject to **GDPR**, **EU CRA**, and **UK PSTI**. The tiers are:

1. **Wearable** — BLE heart-rate sensor (simulated by `edge/wearable.py`)
2. **Edge gateway** — mobile app acting as BLE ↔ HTTPS bridge (`edge/gateway.py`)
3. **Cloud API + DB** — Flask service with MongoDB Atlas backend (`cloud/cloud.py`)

## Critical assets (per the data contract)

| Asset | Tier | CIA sensitivity |
|-------|------|-----------------|
| Patient heart-rate time-series | all three | C: high, I: high, A: medium |
| `patient_id` → identity linkage | cloud DB | C: very high (GDPR special category) |
| HMAC shared secret | wearable ↔ gateway | C: very high (its compromise invalidates A1 defence) |
| JWT signing key | cloud | C: very high |
| MongoDB credentials | cloud ↔ DB | C: very high |

## Trust boundaries

- TB-1: wearable ⇄ gateway (BLE link, physical proximity)
- TB-2: gateway ⇄ cloud (public internet)
- TB-3: cloud app ⇄ database (intra-cloud, but still an isolated boundary)

## Focal threats (the two the assignment requires)

### Threat 1 — BLE-link tampering / replay
- **STRIDE:** Tampering + Spoofing of origin
- **Vector:** adversary in BLE range captures plaintext JSON, mutates `heart_rate` or re-broadcasts a stale packet
- **Vulnerabilities exploited:** BLE link unauthenticated and unencrypted at the application layer; no message-integrity code; no freshness / nonce tracking
- **Adversary capability:** radio access, no prior credentials
- **Primary defence:** HMAC-SHA256 with nonce cache (LYZ)
- **Residual defence:** AI-IDS (ZYM) covers the case where the HMAC key itself is stolen

### Threat 2 — NoSQL injection + unauthorised exfiltration
- **STRIDE:** Information Disclosure + Elevation of Privilege
- **Vector:** attacker POSTs a JSON payload whose field values are MongoDB query operators (`{"$ne": null}`), and/or queries endpoints with no auth or with an over-scoped token
- **Vulnerabilities exploited:** app forwards user-supplied JSON unvalidated to `pymongo`; no authentication middleware; no scope enforcement
- **Adversary capability:** internet only
- **Primary defence:** Pydantic strict schema (ZYM) + JWT zero-trust middleware (ZYM)

## Out-of-scope (acknowledged, not modelled)

- Denial of service (rate limiting listed as future work)
- Side-channel cryptanalysis on HMAC / JWT signing keys
- Cloud provider compromise (MongoDB Atlas trusted)
- Supply-chain attacks on npm / PyPI packages

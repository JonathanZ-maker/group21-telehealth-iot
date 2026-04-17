# Risk Matrix — Group 21

**Used by:** CW1 Page 3  
**Format:** 2×2 likelihood × impact (per the assignment's "simple risk matrix" guidance)

---

## Scoring scale

| Dimension | Low (1) | High (2) |
|-----------|---------|----------|
| **Likelihood** | Requires insider access or highly targeted effort | Feasible for a remote or proximity adversary with public tools |
| **Impact** | Single-record harm, no regulatory trigger | Multi-patient harm or triggers GDPR / CRA notification |

**Priority = Likelihood × Impact** (range 1–4). Anything ≥ 3 is high-priority.

---

## Risk register (fill in as owners complete their analyses)

| ID | Threat | Owner | Likelihood | Impact | Priority | Primary mitigation |
|----|--------|-------|------------|--------|----------|--------------------|
| R1.1 | BLE sniffing of plaintext heart-rate | LKK | 2 | 2 | **4** | HMAC doesn't fix eavesdropping — discussed as residual in report |
| R1.2 | BLE packet tampering (inject extreme values) | LKK | 2 | 2 | **4** | HMAC-SHA256 (LYZ) |
| R1.3 | BLE replay of stale readings | LKK | 2 | 2 | **4** | Nonce cache + freshness window (LYZ) |
| R1.4 | Key-compromise → HMAC-valid semantic attack | LKK | 1 | 2 | **2** | AI-IDS anomaly detection (ZYM) |
| R2.1 | Unauthenticated cloud access | YYX | 2 | 2 | **4** | JWT middleware (ZYM) |
| R2.2 | NoSQL operator injection | YYX | 2 | 2 | **4** | Pydantic strict schema (ZYM) |
| R2.3 | Over-scoped token → privilege escalation | YYX | 1 | 2 | **2** | JWT scope claims (ZYM) |
| R2.4 | DB exfiltration by passive MITM on cloud link | YYX | 1 | 2 | **2** | HTTPS/TLS transport (LYZ) |

---

## 2×2 matrix view

```
             IMPACT →
            Low (1)      High (2)
  L   ┌──────────────┬──────────────┐
  I   │              │   R1.4       │
  K   │              │   R2.3       │
  E   │   (none)     │   R2.4       │
  L   │              │              │
  I   ├──────────────┼──────────────┤
  H   │              │   R1.1       │
  O   │              │   R1.2, R1.3 │
  O   │   (none)     │   R2.1, R2.2 │
  D   │              │              │
  ↓   └──────────────┴──────────────┘
```

Every risk we mitigate in CW2 sits in the top-right quadrant — priorities 3–4.

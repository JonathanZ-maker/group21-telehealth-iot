# Attack 1 — BLE Link Sniffing, Tampering & Replay (LKK)

**Folder:** `attack/`  
**File to write:** `attack/attack1_ble.py`  
**Owner:** LKK  
**Counter-defence:** LYZ's HMAC + ZYM's AI-IDS

---

## 🎯 What this attack must demonstrate (CW1 requirements)

The assignment requires **realistic attack scenarios** with an **attack chain analysis** and a **code/tool-based demonstration**. For Attack 1 you should reproduce three sub-attacks that together tell a full story:

| Sub-attack | What the attacker does | Expected outcome without defence |
|-----------|------------------------|----------------------------------|
| **A1.1 Sniff** | Capture plaintext packets between wearable and gateway | Read patient_id + heart_rate of someone else |
| **A1.2 Tamper** | Modify a captured packet (e.g. heart_rate 75 → 275) and re-send | Gateway accepts it, cloud stores false clinical data |
| **A1.3 Replay** | Re-send an old valid packet later | Gateway accepts a stale reading as current |

---

## 🛠️ How to implement it

Because we simulate BLE over HTTP, you don't need a real BLE sniffer — a simple MITM script that sits between `wearable.py` and `gateway.py` is both realistic and clearly presentable in the video.

Two equivalent approaches:

### Option A — Active MITM proxy (recommended)
Run your script as a proxy on port 8001. Point `wearable.py` at it (`GATEWAY_URL=http://127.0.0.1:8001`). Your proxy:
1. Receives the packet
2. Logs it (= A1.1 sniff, prints cleartext)
3. Optionally mutates `heart_rate` (= A1.2 tamper)
4. Optionally resends it a second time after N seconds (= A1.3 replay)
5. Forwards to the real gateway on port 8000

### Option B — Passive capture + separate attacker client
Capture once by logging, then write a standalone attacker client that pushes mutated / replayed packets to port 8000 directly.

Either is fine; Option A is visually more compelling for the video.

---

## 📜 Attack chain analysis (for CW1 Page 4)

Write the narrative in this file's header (as a docstring) AND copy it into the report:

1. Adversary position: same WiFi / Bluetooth range, no credentials required
2. Observation: traffic is plaintext JSON → patient_id, heart_rate exposed
3. Mutation: change heart_rate to a medically meaningful extreme
4. Injection: forward the tampered packet
5. Impact: gateway accepts, cloud stores, clinician receives a false alert or misses a real one

---

## 📸 Artifacts to capture for the report

- [ ] Screenshot: sniffed cleartext packet printed by your proxy
- [ ] Screenshot: cloud DB record showing a tampered heart_rate value
- [ ] Screenshot: timestamp showing a replayed packet stored twice
- [ ] Attack-chain flow diagram (draw.io, commit the .png under `report/figures/attack1_chain.png`)

---

## 🧱 After LYZ deploys HMAC (defence validation)

Once LYZ's HMAC + nonce check is live, rerun your three sub-attacks. Expected:
- A1.1 (sniff): still possible (HMAC doesn't encrypt) — we discuss that in the report's "residual risk"
- A1.2 (tamper): **HMAC rejects — 401**
- A1.3 (replay): **HMAC nonce cache rejects — 401**

Capture the rejection screenshots — these are what Page 2 of CW2 shows.

---

## 🧱 After ZYM's AI-IDS is live (extra defence validation)

Add a fourth sub-attack that bypasses HMAC (assume the shared key is compromised — a realistic insider / firmware-extraction threat):

**A1.4 Key-compromise semantic attack**: sign a malicious heart_rate value with the real key.

Expected: HMAC passes, AI-IDS fires. Screenshot the AI-IDS `ALERT` log line.

This is the hook that justifies ZYM's AI-IDS module in the defence report.

---

## ✅ Done when

- [ ] `attack/attack1_ble.py` runs end-to-end
- [ ] A1.1, A1.2, A1.3 all work against the undefended gateway
- [ ] A1.2 and A1.3 blocked by LYZ's HMAC
- [ ] A1.4 blocked by ZYM's AI-IDS
- [ ] Five screenshots captured and dropped into `report/figures/`
- [ ] Risk entry in `docs/RISK_MATRIX.md` is filled in (likelihood × impact)

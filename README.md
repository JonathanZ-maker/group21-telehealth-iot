# Group 21 — Privacy-Preserving Telehealth IoT System

> **Course:** ELEC0138 Security and Privacy — Project Assignment 2025/2026  
> **Report title:** *Resilient Security: Threat Modeling and Defensive Strategies for Connected Healthcare Wearable IoT Systems*  
> **Deadline:** 24 April 2026, 4 pm

---

## 👋 START HERE — 1-minute orientation for every team member

1. Find your row in the **task ownership table** below.
2. Open the file in the `"Your task doc"` column — it is written for **you** and lists exactly what you need to deliver, by when, and what interfaces to respect.
3. Skim the **data contract** at the bottom of this page — it is the one thing that keeps our four modules talking to each other.
4. Before you push code, check the **integration contract** of the layer you work in (gateway / cloud / attack).

| Member | Role | Layer | Your task doc |
|--------|------|-------|---------------|
| **LKK** | Data + Red-team Attack 1 | Wearable / BLE link | [`edge/TASKS_LKK.md`](edge/TASKS_LKK.md) + [`attack/TASKS_LKK.md`](attack/TASKS_LKK.md) + [`data/TASKS_LKK.md`](data/TASKS_LKK.md) |
| **LYZ** | Edge gateway + Blue-team HMAC defence | Gateway | [`edge/TASKS_LYZ.md`](edge/TASKS_LYZ.md) |
| **YYX** | Cloud service + Red-team Attack 2 | Cloud API + DB | [`cloud/TASKS_YYX.md`](cloud/TASKS_YYX.md) + [`attack/TASKS_YYX.md`](attack/TASKS_YYX.md) |
| **ZYM** | Blue-team: DP + Pydantic + JWT (+ AI-IDS extension) | Edge + Cloud | [`zym_defense/INTEGRATION.md`](zym_defense/INTEGRATION.md) |

---

## 🏛️ System architecture

```
 ┌────────────────┐    BLE-style       ┌────────────────┐    HTTPS     ┌────────────────┐
 │  wearable.py   │  JSON + HMAC sig   │  gateway.py    │  JSON body   │  cloud.py      │
 │  (LKK)         │ ─────────────────▶ │  (LYZ)         │ ───────────▶ │  (YYX)         │
 │  emits 1 Hz    │                    │                │              │                │
 │  heart-rate    │                    │  ① HMAC check  │              │  ③ JWT check   │
 │                │                    │  ② AI-IDS ★    │              │  ④ Pydantic ★  │
 │                │                    │  ③ DP noise ★  │              │  ⑤ Mongo store │
 └────────────────┘                    └────────────────┘              └────────────────┘
                                            │                                  │
        Attack 1 (LKK): sniff ▲             │                                  │
                        tamper ▲            │                                  │
                        replay ▲            │                                  │
                                            │          Attack 2 (YYX):        │
                                            │          NoSQL injection ───────┘
                                                       unauthorised read

 ★  = modules owned by ZYM; see `zym_defense/INTEGRATION.md`
```

---

## 📁 Repository layout

```
.
├── README.md                 ← you are here
├── requirements.txt          ← pip install -r requirements.txt
├── .gitignore
│
├── edge/                     ← LYZ (gateway) + LKK (wearable)
│   ├── wearable.py           ← LKK: reads CSV, emits JSON + HMAC
│   ├── gateway.py            ← LYZ: Flask/FastAPI, HMAC verify, key rotation
│   ├── TASKS_LKK.md          ← LKK's to-do list for this folder
│   └── TASKS_LYZ.md          ← LYZ's to-do list for this folder
│
├── cloud/                    ← YYX
│   ├── cloud.py              ← YYX: Flask + MongoDB Atlas
│   └── TASKS_YYX.md
│
├── attack/                   ← red-team scripts (kept separate for clarity)
│   ├── attack1_ble.py        ← LKK: sniff / tamper / replay
│   ├── attack2_nosql.py      ← YYX: NoSQL injection
│   ├── TASKS_LKK.md
│   └── TASKS_YYX.md
│
├── zym_defense/              ← ZYM — all ZYM's blue-team code
│   ├── cloud_schema.py       ← Pydantic strict validation
│   ├── cloud_auth.py         ← JWT zero-trust middleware
│   ├── gateway_dp.py         ← Laplace differential privacy
│   ├── gateway_ai_ids.py     ← Isolation-Forest AI-IDS (extension)
│   ├── models/               ← trained iforest.pkl lands here
│   ├── tests/                ← unit + experimental scripts producing figures
│   ├── figures/              ← PNGs used in the report
│   └── INTEGRATION.md        ← how LYZ and YYX wire ZYM's modules in
│
├── data/                     ← LKK
│   ├── raw/                  ← original Kaggle CSV, untouched
│   ├── processed/            ← cleaned heart_rate_cleaned.csv
│   └── TASKS_LKK.md          ← data-source and preprocessing spec
│
├── docs/                     ← team-wide docs (not per-member)
│   ├── DATA_CONTRACT.md      ← the JSON packet schema everyone must respect
│   ├── THREAT_MODEL.md       ← shared threat model used in CW1
│   ├── RISK_MATRIX.md        ← 2×2 risk matrix (CW1 requirement)
│   └── COMPLIANCE.md         ← GDPR / CRA / PSTI mapping
│
├── report/                   ← final deliverable
│   ├── CW1.tex (or .md)      ← Coursework 1, 5 pages
│   ├── CW2.tex (or .md)      ← Coursework 2, 5 pages
│   └── figures/              ← figures linked from the report (copied from zym_defense/figures etc.)
│
├── presentation/             ← 5-minute video material
│   ├── script.md             ← narration / shot list
│   └── demo_recording.md     ← notes on how each scene was captured
│
├── scripts/                  ← top-level runner scripts
│   ├── run_pipeline.sh       ← start wearable + gateway + cloud end-to-end
│   └── run_experiments.sh    ← reproduce every figure in the report
│
└── .github/
    └── CODEOWNERS            ← git shows blame per directory
```

---

## ⚡ Quick start (for anyone cloning the repo)

### Prerequisites
- Python ≥ 3.10
- A MongoDB Atlas free-tier cluster (YYX shares the connection URI via the group chat — **never commit it**)

### Setup
```bash
git clone git@github.com:<org>/group21-telehealth-iot.git
cd group21-telehealth-iot
python -m venv .venv
source .venv/bin/activate          # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                # then fill in your secrets — file is gitignored
```

### Run the end-to-end defended pipeline
```bash
bash scripts/run_pipeline.sh
```

### Reproduce every figure in the report
```bash
bash scripts/run_experiments.sh
```

---

## 📜 Data contract — the single source of truth

Every packet crossing any boundary in this system looks like this:

```json
{
  "patient_id": "P001",
  "timestamp":  1713355200,
  "heart_rate": 78.5,
  "nonce":      "a3f7c1b2...",
  "hmac_sig":   "c91ebd..."
}
```

| Field | Type | Range | Who sets it | Who reads it |
|-------|------|-------|-------------|--------------|
| `patient_id` | str, 1–64 chars, no `$` prefix | — | LKK (wearable) | everyone |
| `timestamp` | int (unix seconds) | ≥ 0 | LKK (wearable) | LYZ (replay check), YYX |
| `heart_rate` | float | 20.0 – 250.0 BPM | LKK (wearable) | LYZ (HMAC covers it), ZYM (AI-IDS + DP), YYX (store) |
| `nonce` | str, ≤128 chars | — | LKK (wearable) | LYZ (replay defence) |
| `hmac_sig` | str, ≤128 chars | — | LKK (wearable) | LYZ (verify) |

Full specification, rationale, and rules for adding fields: [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

---

## 🚦 Branching & commit rules (please respect these — IPAC evidence)

- `main` is protected. **Never push to main directly.**
- Each person works on a feature branch: `feat/lkk`, `feat/lyz`, `feat/yyx`, `feat/zym`, etc.
- Open a pull request into `main` when your module is self-contained and tested. Tag at least one teammate to review.
- Commit from your real GitHub account (the one linked to your UCL email). Git blame is **the** evidence of individual contribution for IPAC.
- Do not edit files outside your own directory without asking the owner.

---

## 📅 Milestones

| Date | Milestone | Owner |
|------|-----------|-------|
| Apr 17 | Repo skeleton committed, every member has read their `TASKS_*.md` | all |
| Apr 19 | Phase 0 pipeline end-to-end dry run (no attacks, no defences) | LKK + LYZ + YYX |
| Apr 20 | Attack 1 + Attack 2 reproducible | LKK + YYX |
| Apr 21 | Defences integrated; logs + screenshots captured | ZYM + LYZ |
| Apr 22 | Experiments + figures generated | ZYM + LKK |
| Apr 23 | Report drafts complete, video recorded | all |
| Apr 24 | Individual contribution statements, final PDF + video link | all |

---

## 📨 Submission checklist (ELEC0138 rubric)

- [ ] 10-page PDF report, combined CW1 + CW2, using the Moodle template
- [ ] Individual contribution statement (≤200 words each) inserted per member
- [ ] YouTube (or public link) to ≤5-minute demo video
- [ ] Public GitHub link (this repo, **made public before submission**)
- [ ] Data repository link (Kaggle source cited in `data/TASKS_LKK.md`)
- [ ] All four blue-team modules running
- [ ] Both red-team attack scripts reproducible
- [ ] GDPR / CRA / PSTI compliance table in the report (`docs/COMPLIANCE.md`)

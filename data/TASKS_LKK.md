# Data Pipeline — Tasks for LKK

**Folder:** `data/`  
**Owner:** LKK  
**Graded part of the assignment:** "10% — data sources and how they were pre-processed"

---

## 🎯 What you need to deliver

1. A single cleaned CSV: `data/processed/heart_rate_cleaned.csv`
2. A short dataset README: `data/raw/README.md` explaining provenance (Kaggle URL, licence, citation)
3. A reproducible cleaning script: `scripts/clean_data.py`
4. One paragraph + one small table for the report describing the data and the cleaning decisions

---

## 📥 Step 1 — Pick and download the dataset

Recommended (any one is fine, but document which one):

| Option | Why it fits |
|--------|-------------|
| **PhysioNet MIMIC-III Waveform / MIMIC-IV** (clinical HR) | Strong clinical realism; big; requires credentialing — overkill for this project |
| **Kaggle "Heart Rate Time Series" / PPG-DaLiA** | Easy download; already cleaned; realistic BPM values |
| **UCI HAR dataset** (has HR-like signals) | Pre-split train/test |

Pick one, put the original unmodified file in `data/raw/`, and write a `data/raw/README.md` with:
- dataset name
- URL and access date
- licence (important — cite it in the report's compliance section)
- brief description (n subjects, sampling rate, total records)

---

## 🧹 Step 2 — Clean and normalise to our schema

**Our packet schema** (from `docs/DATA_CONTRACT.md`):

```
patient_id : str, 1–64 chars
timestamp  : int, unix seconds
heart_rate : float, 20.0 – 250.0
```

Create `scripts/clean_data.py` that produces `data/processed/heart_rate_cleaned.csv` with exactly those columns.

**Cleaning rules to apply (document each in the script as comments):**

1. **Drop NaN / empty rows** — log the count removed
2. **Filter physiologically implausible values** — drop where `heart_rate < 20` or `> 250`
3. **Deduplicate on (patient_id, timestamp)** — keep first
4. **Ensure timestamps are int** — if source uses datetime strings, `int(dt.timestamp())`
5. **Normalise patient_id to string** — pad with zeros for short IDs (e.g. `"P001"` not `"1"`)
6. **Sort by (patient_id, timestamp)** — matters for AI-IDS rolling windows

Example skeleton:

```python
import pandas as pd

df = pd.read_csv("data/raw/<your_file>.csv")
before = len(df)

# Rule 1
df = df.dropna(subset=["heart_rate"])
# Rule 2
df = df[(df["heart_rate"] >= 20) & (df["heart_rate"] <= 250)]
# Rule 3
df = df.drop_duplicates(subset=["patient_id", "timestamp"], keep="first")
# Rule 4
df["timestamp"] = df["timestamp"].astype(int)
# Rule 5
df["patient_id"] = df["patient_id"].astype(str).str.zfill(4).radd("P")
# Rule 6
df = df.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)

print(f"kept {len(df)} / {before} rows")
df.to_csv("data/processed/heart_rate_cleaned.csv", index=False)
```

---

## 📊 Step 3 — Produce dataset statistics for the report

Append to the script so running it also prints (and saves to `data/processed/stats.txt`):
- total rows, total patients
- heart_rate min / max / mean / std per patient
- distribution bins (e.g. `[0,60), [60,80), [80,100), [100,250]`)

These numbers go straight into the CW1 Page 1 "Assets" table and the CW1 Page 3 impact-analysis discussion.

---

## 🔗 Downstream consumers of this file

| Consumer | File | How they read it |
|----------|------|------------------|
| LKK (you) | `edge/wearable.py` | streams rows at ~1 Hz to the gateway |
| ZYM | `zym_defense/tests/test_ai_ids.py` | trains AI-IDS on this CSV |
| ZYM | `zym_defense/tests/test_dp.py` | evaluates privacy–utility trade-off |

So: **columns and types must match the data contract exactly**, otherwise their scripts break.

---

## ✅ Done when

- [ ] `data/raw/README.md` exists and names the dataset + URL + licence
- [ ] `scripts/clean_data.py` runs end-to-end in < 30 s
- [ ] `data/processed/heart_rate_cleaned.csv` exists and has the right columns
- [ ] `data/processed/stats.txt` contains the summary numbers
- [ ] You have committed a screenshot of the terminal output (for the report)

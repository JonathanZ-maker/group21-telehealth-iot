"""
scripts/clean_data.py — LKK owns this file.

Reads data/raw/<source>.csv and produces
data/processed/heart_rate_cleaned.csv and data/processed/stats.txt.

Refer to data/TASKS_LKK.md for the full specification.

Placeholder — LKK please replace the body below with the real cleaning
pipeline (rules 1–6 in TASKS_LKK.md).
"""

from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main() -> None:
    print("[clean_data] placeholder — see data/TASKS_LKK.md")
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    sources = list(RAW_DIR.glob("*.csv"))
    if not sources:
        print(f"[clean_data] no CSVs under {RAW_DIR}. Add one and re-run.")
        return
    print(f"[clean_data] found {len(sources)} raw CSV(s): "
          f"{[p.name for p in sources]}")


if __name__ == "__main__":
    main()

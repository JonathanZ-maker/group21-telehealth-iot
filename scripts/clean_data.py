"""
scripts/clean_data.py — LKK owns this file.

Reads data/raw/<source>.csv and produces
data/processed/heart_rate_cleaned.csv and data/processed/stats.txt.

Implemented by LKK: Handles wide-to-long conversion, 1Hz downsampling, 
and strictly enforces rules 1-6 from TASKS_LKK.md.
"""

import pandas as pd
import numpy as np
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

def main() -> None:
    print("Launching IoMT data cleaning pipeline (LKK Pipeline)...")
    
    # Ensure the processed directory exists
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    
    # Automatically find the first CSV file in the raw directory
    sources = list(RAW_DIR.glob("*.csv"))
    if not sources:
        print(f"[clean_data] No raw data found! Please make sure you have put the downloaded CSV into the {RAW_DIR} directory.")
        return
    
    raw_file_path = sources[0]  # Default to reading the first found CSV
    cleaned_file_path = PROC_DIR / "heart_rate_cleaned.csv"
    stats_file_path = PROC_DIR / "stats.txt"
    
    print(f"Found raw file: {raw_file_path.name}, starting processing...")

    try:
        # --- 1. Load original wide-format data ---
        df_raw = pd.read_csv(raw_file_path)
        
        # Preprocess: Generate relative time (in seconds) based on row index (original data interval: 0.5s)
        df_raw['relative_time_sec'] = df_raw.index * 0.5
        
        # Preprocess: Wide-to-long conversion (melt)
        patient_columns = [col for col in df_raw.columns if col != 'relative_time_sec']
        df = df_raw.melt(
            id_vars=['relative_time_sec'], 
            value_vars=patient_columns,
            var_name='patient_id', 
            value_name='heart_rate'
        )
        before_count = len(df)

        # --- 2. Strictly enforce the 6 data cleaning rules from TASKS_LKK.md ---
        
        # Rule 1: Drop NaN / empty rows
        df = df.dropna(subset=["heart_rate"])
        
        # Rule 4 & 1Hz Downsampling: Ensure timestamps are int
        # Filter rows where relative_time_sec is an integer, discard ".5" rows to achieve 1Hz downsampling
        df = df[df['relative_time_sec'] % 1 == 0].copy()
        BASE_UNIX_TIME = 1767225600 # Set a base starting Unix time
        df['timestamp'] = (BASE_UNIX_TIME + df['relative_time_sec']).astype(int)
        
        # Rule 2: Filter physiologically implausible values
        df = df[(df["heart_rate"] >= 20.0) & (df["heart_rate"] <= 250.0)]
        
        # Rule 5: Normalise patient_id to string (e.g. T1 becomes P0001)
        df['patient_id'] = df['patient_id'].astype(str).str.extract(r'(\d+)')[0].astype(str).str.zfill(4).radd("P")
        
        # Remove auxiliary columns
        df = df.drop(columns=['relative_time_sec'])
        
        # Rule 3: Deduplicate on (patient_id, timestamp)
        df = df.drop_duplicates(subset=["patient_id", "timestamp"], keep="first")
        
        # Rule 6: Sort by (patient_id, timestamp)
        df = df.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)
        
        # Strictly follow data contract column order
        df = df[['patient_id', 'timestamp', 'heart_rate']]
        after_count = len(df)
        
        # --- 3. Save cleaned CSV ---
        df.to_csv(cleaned_file_path, index=False)
        print(f"Data cleaning done: row count after melt {before_count} -> after cleaning/downsampling {after_count}")
        print(f"Saved to: {cleaned_file_path}")

        # --- 4. Generate statistics (stats.txt) ---
        total_rows = len(df)
        total_patients = df["patient_id"].nunique()
        patient_stats = df.groupby("patient_id")["heart_rate"].agg(['min', 'max', 'mean', 'std']).round(2)
        
        bins = [0, 60, 80, 100, 250]
        labels = ['[0,60)', '[60,80)', '[80,100)', '[100,250]']
        distribution = pd.cut(df['heart_rate'], bins=bins, labels=labels, right=False).value_counts().sort_index()

        stats_output = (
            "======================================\n"
            "      Dataset Statistics Summary      \n"
            "======================================\n\n"
            f"Total Rows (Cleaned & 1Hz): {total_rows}\n"
            f"Total Unique Patients: {total_patients}\n\n"
            "--- Heart Rate Distribution ---\n"
            f"{distribution.to_string()}\n\n"
            "--- Per Patient Stats (Min / Max / Mean / Std) ---\n"
            f"{patient_stats.to_string()}\n"
        )

        with open(stats_file_path, "w") as f:
            f.write(stats_output)
            
        print(f"Statistics have been generated and saved to: {stats_file_path}")

    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    main()
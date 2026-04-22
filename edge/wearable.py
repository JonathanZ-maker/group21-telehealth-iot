"""
edge/wearable.py — LKK owns this file.

Simulates a smart watch sending IoT telemetry to the Gateway.
Reads from data/processed/heart_rate_cleaned.csv, constructs JSON packets,
signs them with HMAC-SHA256, and POSTs them to the gateway.
"""

import csv
import json
import time
import hmac
import hashlib
import os
import secrets
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constant configuration
CSV_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "heart_rate_cleaned.csv"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000/upload")

# You must create a .env file in the project root with HMAC_DEVICE_SECRET=your_super_secret_key
try:
    SECRET = os.environ["HMAC_DEVICE_SECRET"].encode()
except KeyError:
    print("Error: HMAC_DEVICE_SECRET not found. Please create a .env file in the project root and set this variable!")
    exit(1)


def sign(payload: dict) -> dict:
    """Generate nonce and sign packet using HMAC-SHA256"""
    payload["nonce"] = secrets.token_hex(16)

    # Strictly follow canonicalization: sort keys and remove spaces to ensure byte-identical serialization
    to_sign = json.dumps(
        {k: payload[k] for k in ("patient_id", "timestamp", "heart_rate", "nonce")},
        sort_keys=True,
        separators=(",", ":")
    ).encode()

    payload["hmac_sig"] = hmac.new(SECRET, to_sign, hashlib.sha256).hexdigest()
    return payload


def send_packet(payload: dict, max_retries: int = 3) -> bool:
    """Send packet with retry and backoff mechanism"""
    for attempt in range(1, max_retries + 1):
        try:
            # Set a short timeout to prevent blocking
            response = requests.post(GATEWAY_URL, json=payload, timeout=2.0)
            response.raise_for_status()  # Raise exception for 4xx/5xx responses
            return True
        except requests.RequestException as e:
            if attempt < max_retries:
                # Log the error and wait 2 seconds before retrying (backoff)
                time.sleep(2)
            else:
                print(f"[skip] Packet dropped after 3 retries. Error: {e}")
                return False


def main():
    # 1. Parse command line arguments
    parser = argparse.ArgumentParser(description="Wearable IoT Simulator")
    parser.add_argument("--speed", type=float, default=1.0, help="Sending speed multiplier (e.g. 10 for 10x speed)")
    parser.add_argument("--patient", type=str, default=None, help="Only send data for the specified patient_id (e.g. P001)")
    args = parser.parse_args()

    if not CSV_FILE_PATH.exists():
        print(f"Cannot find cleaned data file: {CSV_FILE_PATH}")
        print("Please run scripts/clean_data.py first!")
        return

    print(f"Starting wearable simulator | Target gateway: {GATEWAY_URL} | Speed: {args.speed}x")
    if args.patient:
        print(f"Filtering enabled: Only sending data for patient {args.patient}")

    # 2. Infinite loop to replay the CSV
    loop_count = 1
    while True:
        print(f"\n--- Begin data replay round {loop_count} ---")

        with open(CSV_FILE_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Filter specific patient
                if args.patient and row["patient_id"] != args.patient:
                    continue

                # Build payload, ensure correct type conversion (CSV reads as strings)
                payload = {
                    "patient_id": row["patient_id"],
                    "timestamp": int(time.time()),
                    "heart_rate": float(row["heart_rate"])
                }

                # Sign the payload
                signed_payload = sign(payload)

                # Send and print compact log
                success = send_packet(signed_payload)
                if success:
                    print(f"[send] {payload['patient_id']} ts={payload['timestamp']} hr={payload['heart_rate']}")

                # Simulate BLE sending interval (1Hz) and apply speed multiplier
                time.sleep(1.0 / args.speed)

        loop_count += 1

if __name__ == "__main__":
    main()
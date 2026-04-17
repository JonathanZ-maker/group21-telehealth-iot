# Security Policy — Group 21 Telehealth IoT System

## Reporting a vulnerability

If you believe you have found a security vulnerability in this project, please do **not** open a public issue.

Instead, contact the team privately via the group email listed in the report's cover page, or open a private security advisory on GitHub (Security → Advisories → Report a vulnerability).

We will acknowledge receipt within 72 hours and aim to publish a fix — or a documented mitigation — within 30 days.

## Minimum supported period

This repository is a student coursework deliverable for **UCL ELEC0138 (2025/2026)**. Active maintenance is provided from the project start until **30 June 2026**. After that date the code is provided *as-is* for educational reference only.

## Scope

In scope:
- `edge/gateway.py` HMAC + replay defences
- `cloud/cloud.py` JWT and schema middleware
- `zym_defense/` differential-privacy, AI-IDS, authentication, input-validation modules

Out of scope:
- Third-party cloud provider security (MongoDB Atlas)
- Denial-of-service attacks
- Vulnerabilities in pinned upstream dependencies (report those upstream)

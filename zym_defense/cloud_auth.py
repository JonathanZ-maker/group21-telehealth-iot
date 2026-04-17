"""
cloud_auth.py
=============
JWT-based zero-trust authorisation middleware for the telehealth cloud API.

Defence target
--------------
Attack 2 — Unauthorised data exfiltration.
Even when payloads are schema-valid (surviving cloud_schema.py), every
request must still prove it originates from an enrolled, non-revoked
principal with the right scope. No implicit network trust, no session
cookies, no "behind the firewall" assumptions.

Design choices & justification (for the report)
-----------------------------------------------
1. HS256 symmetric signing — acceptable in a single-tenant enterprise
   deployment where the key is provisioned via a secure channel. For a
   real multi-org deployment RS256 + JWKS rotation would be preferable;
   discussed in CW2 Trade-offs.
2. Short expiry (`exp` ~ 15 min) + explicit `iat`, `nbf`, `jti` claims
   — mitigates replay of stolen tokens.
3. Scope-based authorisation via `scope` claim — e.g. "ingest:write",
   "readings:read". A device token for ingest cannot query the DB.
4. In-memory revocation set keyed by `jti` — demonstrates that a
   compromised device can be instantly cut off without redeploying.
5. Fail-closed decorator — missing / malformed / expired / revoked
   token all produce HTTP 401 with a minimal error code (no leak of
   which check failed, to avoid oracle behaviour).

Author: ZYM (Group 21)
Module: Defence 2 — Cloud layer / Access control
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from functools import wraps
from typing import Callable, Iterable

import jwt  # PyJWT
from flask import Request, g, jsonify, request

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("zym.cloud_auth")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] [JWT] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# In production this comes from a KMS / secrets manager. For the prototype
# we load from an env var and fall back to a random per-process secret so
# the demo always runs, while making it obvious the secret must be set.
_SECRET = os.environ.get("ZYM_JWT_SECRET") or secrets.token_urlsafe(48)
_ALGO = "HS256"
_ISSUER = "group21.telehealth.cloud"
_DEFAULT_TTL = 15 * 60  # 15 minutes

# Simple in-process revocation list. Keyed by jti. A real deployment would
# use Redis with TTL = token exp so entries self-expire.
_REVOKED_JTI: set[str] = set()


# ---------------------------------------------------------------------------
# Token issuance — used by a trusted enrolment endpoint / CLI
# ---------------------------------------------------------------------------
def issue_token(subject: str, scopes: Iterable[str], ttl_seconds: int = _DEFAULT_TTL) -> str:
    """
    Mint a JWT for a given principal (e.g. a gateway device id or a
    clinician user id) with an explicit list of scopes.

    Example
    -------
    >>> t = issue_token("gateway-eu-west-01", ["ingest:write"])
    >>> claims = verify_token(t)
    >>> claims["sub"]
    'gateway-eu-west-01'
    """
    now = int(time.time())
    payload = {
        "iss": _ISSUER,
        "sub": subject,
        "iat": now,
        "nbf": now,
        "exp": now + ttl_seconds,
        "jti": secrets.token_hex(8),
        "scope": " ".join(sorted(set(scopes))),
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALGO)
    logger.info("ISSUE  sub=%s  scope=%s  jti=%s  ttl=%ds",
                subject, payload["scope"], payload["jti"], ttl_seconds)
    return token


def revoke(jti: str) -> None:
    """Immediately invalidate a token by its jti claim."""
    _REVOKED_JTI.add(jti)
    logger.warning("REVOKE  jti=%s", jti)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------
class AuthError(Exception):
    """Internal marker — always surfaced as HTTP 401, reason not leaked."""


def verify_token(token: str) -> dict:
    """Raise AuthError on any failure; otherwise return the claims dict."""
    try:
        claims = jwt.decode(
            token,
            _SECRET,
            algorithms=[_ALGO],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "nbf", "sub", "jti", "scope"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthError("expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthError("invalid") from e

    if claims.get("jti") in _REVOKED_JTI:
        raise AuthError("revoked")

    return claims


# ---------------------------------------------------------------------------
# Flask decorator — the one-liner injection point for YYX's cloud.py
# ---------------------------------------------------------------------------
def require_jwt(*required_scopes: str) -> Callable:
    """
    Decorator factory enforcing JWT presence AND required scopes.

    Usage::

        @app.route("/ingest", methods=["POST"])
        @require_jwt("ingest:write")
        def ingest(): ...

        @app.route("/admin/export", methods=["GET"])
        @require_jwt("readings:read", "readings:export")
        def export(): ...
    """

    def deco(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            # 1) Must carry an Authorization: Bearer <token> header
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                logger.warning("BLOCK  reason=missing_bearer  path=%s  peer=%s",
                               request.path, request.remote_addr)
                return jsonify({"error": "unauthorized"}), 401

            token = auth[len("Bearer "):].strip()

            # 2) Signature + expiry + revocation
            try:
                claims = verify_token(token)
            except AuthError as e:
                logger.warning("BLOCK  reason=%s  path=%s  peer=%s",
                               e.args[0], request.path, request.remote_addr)
                return jsonify({"error": "unauthorized"}), 401

            # 3) Scope check — every required scope must be present
            held = set(claims.get("scope", "").split())
            missing = set(required_scopes) - held
            if missing:
                logger.warning(
                    "BLOCK  reason=insufficient_scope  sub=%s  needed=%s  held=%s",
                    claims.get("sub"), sorted(missing), sorted(held),
                )
                return jsonify({"error": "forbidden_scope"}), 401

            # Expose the authenticated principal to the view
            g.jwt_claims = claims
            logger.info("ALLOW  sub=%s  path=%s  scope_used=%s",
                        claims["sub"], request.path, sorted(required_scopes))
            return view(*args, **kwargs)

        return wrapper

    return deco


# ---------------------------------------------------------------------------
# Demo — run `python cloud_auth.py` to reproduce the report screenshots
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("JWT zero-trust defence — demo")
    print("=" * 70)

    # 1) Mint a token for a gateway device
    good = issue_token("gateway-eu-west-01", ["ingest:write"], ttl_seconds=60)
    print(f"\nIssued device token:\n  {good[:40]}...\n")

    # 2) Mint an expired one to demonstrate rejection
    expired = issue_token("gateway-eu-west-01", ["ingest:write"], ttl_seconds=-1)

    # 3) Tamper with a good token
    tampered = good[:-4] + "AAAA"

    # 4) Verify each scenario
    for label, tok in [
        ("VALID", good),
        ("EXPIRED", expired),
        ("TAMPERED", tampered),
        ("EMPTY", ""),
    ]:
        try:
            c = verify_token(tok)
            print(f"  [ALLOW ] {label:<10}  sub={c['sub']}  scope={c['scope']}")
        except AuthError as e:
            print(f"  [BLOCK ] {label:<10}  reason={e.args[0]}")

    # 5) Revocation scenario
    c = verify_token(good)
    revoke(c["jti"])
    try:
        verify_token(good)
    except AuthError as e:
        print(f"  [BLOCK ] REVOKED     reason={e.args[0]}")

    # 6) Scope mismatch — minted ingest token but called /admin/export
    try:
        claims = verify_token(issue_token("gateway-eu-west-01", ["ingest:write"]))
        held = set(claims["scope"].split())
        needed = {"readings:export"}
        missing = needed - held
        print(f"  [BLOCK ] SCOPE-MISS  needed={needed}  held={held}  missing={missing}")
    except AuthError as e:
        print(f"  error: {e}")
    print()

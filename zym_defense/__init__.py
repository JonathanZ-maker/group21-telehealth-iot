"""
zym_defense — Blue-team defence modules for Group 21's Telehealth IoT system.

Author: ZYM

Public API (import directly from submodules to avoid pulling unused deps):

    # Edge (needs numpy, sklearn):
    from zym_defense.gateway_ai_ids import get_detector
    from zym_defense.gateway_dp     import privatise_heart_rate

    # Cloud (needs pydantic, PyJWT, flask):
    from zym_defense.cloud_auth     import require_jwt, issue_token
    from zym_defense.cloud_schema   import validate_payload

We deliberately avoid re-exporting everything at package level, because
gateway-only deployments should not need pydantic/flask, and vice versa.
"""

__version__ = "0.1.0"

"""
gateway_dp.py
=============
Edge-side differential-privacy engine for the telehealth gateway.

Defence target
--------------
Data-security dimension (CW2 requirement #2).
After HMAC verification and AI-IDS anomaly screening, heart-rate values
are perturbed with calibrated Laplace noise before being forwarded to
the cloud. This means:

  * The cloud (and anyone who breaches it later) sees only a noisy
    version of each individual reading — preventing precise profiling.
  * Population-level statistics (mean, trend, distribution) remain
    usable for public-health analytics.

Mechanism
---------
Laplace mechanism. For a numeric query f with L1-sensitivity Δf, adding
noise drawn from Lap(Δf / ε) gives ε-differential privacy (Dwork et al.,
2006).

Parameter justification (covered in CW2 Trade-offs)
---------------------------------------------------
  * Δf (sensitivity). The naïve worst case is the full physiological
    range (250 − 20 = 230 BPM). Applying that directly makes the
    Laplace noise dominate the signal and the release becomes useless.
    We adopt a *bounded-perturbation* model: each reading is first
    clipped to the user's own recent median ± CLIP_WINDOW (default
    ±30 BPM, which comfortably covers physiological minute-to-minute
    variation). The effective per-release sensitivity is therefore
    Δf = 2 * CLIP_WINDOW = 60 BPM, consistent with the technique used
    in industrial DP telemetry systems (e.g. Apple's macOS / iOS
    deployment, which similarly clips contributions before noising).
  * ε = 1.0 default — a commonly cited "strong but usable" budget for
    per-event release in medical telemetry. The bench script sweeps
    ε ∈ {0.1, 0.5, 1.0, 2.0, 5.0} and produces the privacy–utility
    figure used in the report.
  * Per-event budget. We do not implement a global composition tracker
    in this prototype; the report discusses this as a known limitation
    and points to advanced-composition / Rényi-DP as future work.

Author: ZYM (Group 21)
Module: Defence 2 — Edge layer / Data protection
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("zym.gateway_dp")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] [DP] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Physiological bounds — also used by cloud_schema.py
HR_MIN, HR_MAX = 20.0, 250.0

# Clip each reading to (reference ± CLIP_WINDOW) before adding noise.
# "reference" is supplied per-call (e.g. the user's recent median). The
# resulting per-release sensitivity is Δf = 2 * CLIP_WINDOW.
CLIP_WINDOW = float(os.environ.get("ZYM_DP_CLIP_WINDOW", "30.0"))
SENSITIVITY = 2.0 * CLIP_WINDOW           # Δf = 60 BPM with defaults

# ε is read from env for reproducible experiments; defaults to 1.0
DEFAULT_EPSILON = float(os.environ.get("ZYM_DP_EPSILON", "1.0"))


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------
@dataclass
class LaplaceDP:
    """
    Stateless Laplace-mechanism perturber for a bounded scalar query.

    Parameters
    ----------
    epsilon : float
        Per-release privacy budget. Smaller = more privacy, less utility.
    sensitivity : float
        L1 sensitivity of the query. For a single clipped reading this is
        the width of the clip range.
    lo, hi : float
        Post-noise clipping range, re-applied so the cloud never receives
        physiologically impossible values like -40 BPM.
    seed : int | None
        Only for deterministic unit tests; leave None in production.
    """

    epsilon: float = DEFAULT_EPSILON
    sensitivity: float = SENSITIVITY
    clip_window: float = CLIP_WINDOW
    lo: float = HR_MIN
    hi: float = HR_MAX
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.epsilon <= 0:
            raise ValueError("epsilon must be > 0")
        if self.sensitivity <= 0:
            raise ValueError("sensitivity must be > 0")
        self._rng = np.random.default_rng(self.seed)
        self._scale = self.sensitivity / self.epsilon     # b = Δf / ε
        logger.info(
            "INIT   ε=%.3f  Δf=%.1f  b=Δf/ε=%.3f  clip=±%.1f  bounds=[%.1f, %.1f]",
            self.epsilon, self.sensitivity, self._scale,
            self.clip_window, self.lo, self.hi,
        )

    # -- public API --------------------------------------------------------
    def privatise(self, value: float, reference: float | None = None) -> float:
        """
        Return a DP-perturbed copy of `value`.

        Parameters
        ----------
        value : float
            Raw heart-rate reading.
        reference : float or None
            Per-user anchor (e.g. recent median). If None, the midpoint
            of the physiological range is used — the report notes this
            makes the worst-case assumption and is safe but less tight.
        """
        if reference is None:
            reference = 0.5 * (self.lo + self.hi)
        # First clamp the input around the reference so the worst-case
        # sensitivity assumption Δf = 2 * clip_window holds.
        ref_lo = max(self.lo, reference - self.clip_window)
        ref_hi = min(self.hi, reference + self.clip_window)
        clipped = max(ref_lo, min(ref_hi, float(value)))
        noise = self._rng.laplace(loc=0.0, scale=self._scale)
        noisy = clipped + noise
        # Post-clip so downstream systems see physically plausible values.
        released = max(self.lo, min(self.hi, noisy))
        logger.debug("PRIVATISE  raw=%.2f  ref=%.2f  clipped=%.2f  "
                     "noise=%+.2f  released=%.2f",
                     value, reference, clipped, noise, released)
        return released

    def privatise_record(self, record: dict, reference: float | None = None) -> dict:
        """
        Perturb the `heart_rate` field of a record dict in-place and
        return it. Non-numeric records are logged and dropped.
        """
        hr = record.get("heart_rate")
        if not isinstance(hr, (int, float)):
            logger.warning("DROP   non-numeric heart_rate=%r", hr)
            raise ValueError("heart_rate must be numeric")
        record["heart_rate"] = round(self.privatise(hr, reference), 2)
        return record

    # -- theoretical accuracy bound (for the report) -----------------------
    def expected_abs_error(self) -> float:
        """E[|noise|] = b for Laplace(0, b). Useful for the utility table."""
        return self._scale

    def error_percentile(self, p: float = 0.95) -> float:
        """
        Two-sided confidence half-width at level p.
        For Laplace(0,b): |X| ≤ -b * ln(1-p)  with probability p.
        """
        if not 0 < p < 1:
            raise ValueError("p must be in (0, 1)")
        return -self._scale * math.log(1.0 - p)


# ---------------------------------------------------------------------------
# Convenience singleton for the gateway hot path
# ---------------------------------------------------------------------------
_default_engine: LaplaceDP | None = None


def get_engine() -> LaplaceDP:
    """Lazy singleton so the gateway constructs it once per process."""
    global _default_engine
    if _default_engine is None:
        _default_engine = LaplaceDP()
    return _default_engine


def privatise_heart_rate(value: float, reference: float | None = None) -> float:
    """Top-level shortcut used by gateway.py on the hot path."""
    return get_engine().privatise(value, reference)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("Differential-privacy engine — demo")
    print("=" * 70)

    rng = np.random.default_rng(0)
    truth = rng.normal(loc=75, scale=6, size=20).clip(40, 140)
    # In production the reference is each patient's running median;
    # for the demo we use the cohort mean.
    reference = float(np.median(truth))

    for eps in (0.1, 0.5, 1.0, 5.0):
        eng = LaplaceDP(epsilon=eps, seed=42)
        noisy = np.array([eng.privatise(v, reference=reference) for v in truth])
        mae = float(np.mean(np.abs(noisy - truth)))
        print(f"\nε = {eps:>4.1f}  →  b = Δf/ε = {eng._scale:>7.2f}  "
              f"MAE = {mae:>6.2f}  95%-halfwidth = {eng.error_percentile(0.95):>7.2f}")
        print(f"  true :  {np.round(truth[:8], 1).tolist()}")
        print(f"  noisy:  {np.round(noisy[:8], 1).tolist()}")

    print("\nPopulation-mean preservation at ε=1.0, n=10000:")
    eng = LaplaceDP(epsilon=1.0, seed=1)
    big = rng.normal(75, 6, 10000).clip(40, 140)
    ref = float(np.median(big))
    noisy = np.array([eng.privatise(v, reference=ref) for v in big])
    print(f"  true  mean = {big.mean():.3f}")
    print(f"  noisy mean = {noisy.mean():.3f}   (Laplace noise is zero-mean → averages out)")
    print()

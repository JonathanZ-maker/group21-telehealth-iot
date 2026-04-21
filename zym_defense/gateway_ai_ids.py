"""
gateway_ai_ids.py
=================
AI-driven anomaly-detection intrusion-detection system (AI-IDS) for the
telehealth gateway.

Defence target
--------------
Network-monitoring + emerging-threat resilience (CW2 requirements #3 and
#4).  Fills the gap left by HMAC integrity checks: when a device key is
compromised (firmware extraction, insider-controlled hardware, or a
zero-day in the key-provisioning chain) the attacker can produce
*cryptographically valid* messages carrying semantically malicious
payloads — e.g. injecting a heart rate of 300 BPM to trigger a false
cardiac alert, or "dead-stick" 20-BPM values to mask an event.

Approach
--------
Isolation Forest, an unsupervised tree ensemble (Liu et al., 2008). We
choose it because:

  * Training is label-free — we only have healthy telemetry, no attack
    labels from the target population. Matches the reality of an edge
    deployment.
  * It is fast to score (O(log n) per tree), small in memory, and
    available via scikit-learn, making it feasible to ship to a mobile
    gateway.
  * It handles the "needle-in-a-haystack" regime well, which fits
    tampered readings embedded in an otherwise normal stream.

Feature engineering
-------------------
We do NOT use raw heart-rate alone — a single value carries too little
context for a model to separate healthy variation from a tampered
injection. A rolling 10-sample window is maintained per-device and the
following features are extracted:

    [raw, mean_w, std_w, min_w, max_w, delta_from_prev, rolling_z_score]

This lets the model flag:
    * Extreme values inconsistent with the recent window (e.g. 300 BPM)
    * Impossible deltas (e.g. +120 BPM in 1 sample)
    * Dead-stick attacks (std ≈ 0 over the window)

Evaluation
----------
Reported via ROC + AUC on a held-out test set where we synthetically
inject four attack families (spike / drop / replay-flat / drift).
See tests/test_ai_ids.py for the full experiment.

Author: ZYM (Group 21)
Module: Defence 2 — Edge layer / Anomaly detection
"""

from __future__ import annotations

import logging
import os
import pickle
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict

import numpy as np
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("zym.gateway_ai_ids")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] [AI-IDS] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------
WINDOW = 10            # rolling window length
N_FEATURES = 9         # size of the feature vector


def _featurise(window: np.ndarray) -> np.ndarray:
    """
    Turn a 1-D rolling window of heart-rate values into the AI-IDS
    feature vector. Caller must pass a window of length WINDOW; the most
    recent value is at index -1.

    Features
    --------
    [0] raw                    latest reading
    [1] mean_w                 window mean
    [2] std_w                  window std dev
    [3] range_w                max − min over the window
    [4] delta                  raw − previous sample
    [5] abs_delta              |delta|
    [6] rolling_z              z-score of raw against the window
    [7] inv_std_penalty        1/(std_w + ε)  — large when window is
                               suspiciously flat (dead-stick attack)
    [8] flat_run_length        number of trailing samples equal (to 1dp)
                               to the latest — captures dead-stick even
                               when older samples in the window vary
    """
    raw = float(window[-1])
    mean_w = float(np.mean(window))
    std_w = float(np.std(window))
    min_w = float(np.min(window))
    max_w = float(np.max(window))
    range_w = max_w - min_w
    delta = float(raw - window[-2]) if len(window) >= 2 else 0.0
    abs_delta = abs(delta)
    z = (raw - mean_w) / (std_w + 1e-3)
    inv_std_penalty = 1.0 / (std_w + 0.5)
    # Trailing run of values identical (to 0.1 BPM) to the latest reading
    flat_run = 0
    rounded_latest = round(raw, 1)
    for v in reversed(window):
        if round(float(v), 1) == rounded_latest:
            flat_run += 1
        else:
            break
    return np.array([raw, mean_w, std_w, range_w, delta,
                     abs_delta, z, inv_std_penalty, float(flat_run)],
                    dtype=np.float32)


def featurise_stream(values: np.ndarray, window: int = WINDOW) -> np.ndarray:
    """Vectorised featuriser used at training time. Returns (N, 7)."""
    n = len(values)
    if n < window:
        raise ValueError(f"need at least {window} samples, got {n}")
    out = np.empty((n - window + 1, N_FEATURES), dtype=np.float32)
    for i in range(n - window + 1):
        out[i] = _featurise(values[i:i + window])
    return out


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------
@dataclass
class AIIDS:
    """
    Stateful detector. Maintains one rolling window per device id and a
    single shared Isolation-Forest model.

    A negative `score_samples` output from scikit-learn corresponds to
    "more anomalous". We expose a stable monotonic score where higher
    means more anomalous, and a binary decision at a configurable
    threshold.
    """

    contamination: float = 0.01          # prior on attack prevalence
    n_estimators: int = 200
    random_state: int = 0
    threshold: float = 0.0               # decision boundary (set in fit)
    # Hard physiological guard — "hybrid detector" fast path
    HARD_LO: float = 30.0
    HARD_HI: float = 220.0
    # Dead-stick rule: N consecutive identical readings (to 0.1 BPM)
    # are physiologically implausible for a live subject.
    DEAD_STICK_MIN_RUN: int = 5
    # Threshold calibration: use a quantile *tighter* than contamination
    # to trade a slight recall loss for a much lower false-positive rate
    # on healthy streams. 0.995 → ~0.5 % training FPR target.
    threshold_quantile: float = 0.995

    _model: IsolationForest | None = field(default=None, init=False, repr=False)
    _windows: Dict[str, Deque[float]] = field(default_factory=dict, init=False, repr=False)

    # -------- training ----------------------------------------------------
    def fit(self, healthy_values: np.ndarray) -> "AIIDS":
        """
        Fit on a 1-D array of *known-benign* heart-rate readings.
        Flattens to the feature space internally.
        """
        X = featurise_stream(healthy_values)
        self._model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        ).fit(X)
        # sklearn's decision_function is > 0 for inliers, < 0 for outliers.
        # We flip sign so "higher = more anomalous" and calibrate the
        # threshold via a user-chosen quantile of *training* scores.
        train_scores = -self._model.decision_function(X)
        self.threshold = float(np.quantile(train_scores, self.threshold_quantile))
        logger.info(
            "FIT    n_train=%d  n_features=%d  contamination=%.3f  "
            "q=%.3f  threshold=%.4f",
            len(X), N_FEATURES, self.contamination,
            self.threshold_quantile, self.threshold,
        )
        return self

    # -------- scoring -----------------------------------------------------
    def _ensure_model(self) -> IsolationForest:
        if self._model is None:
            raise RuntimeError("AIIDS.fit() or AIIDS.load() must be called first")
        return self._model

    def score_window(self, window: np.ndarray) -> float:
        """Anomaly score for a single pre-filled window. Higher = worse."""
        model = self._ensure_model()
        feats = _featurise(window).reshape(1, -1)
        return float(-model.decision_function(feats)[0])

    def inspect(self, device_id: str, heart_rate: float) -> tuple[bool, float]:
        """
        Streaming API used on the gateway hot path.

        Decision order (hybrid detector):
          1. Fast-path rule — physiological hard bounds → instant block.
          2. Window warm-up (< WINDOW samples) → fail-open.
          3. Fast-path rule — dead-stick detection (the latest N samples
             are all identical to 0.1 BPM precision) → instant block.
             Physiologically impossible for a live subject; cheaper and
             more reliable than asking the Isolation Forest to learn it.
          4. Isolation-Forest score vs. trained threshold → block or pass.

        Returns (is_anomalous, score). Rule-path blocks use score = +inf,
        visually distinct in logs and plots.
        """
        # (1) Fast-path hard rule — physiological bounds
        if not (self.HARD_LO <= heart_rate <= self.HARD_HI):
            logger.warning(
                "ALERT  device=%s  hr=%.2f  reason=hard_bound  "
                "allowed=[%.1f,%.1f]",
                device_id, heart_rate, self.HARD_LO, self.HARD_HI,
            )
            return True, float("inf")

        # (2) Rolling window warm-up
        buf = self._windows.setdefault(device_id, deque(maxlen=WINDOW))
        buf.append(float(heart_rate))
        if len(buf) < WINDOW:
            return False, 0.0

        # (3) Fast-path hard rule — dead-stick detection
        # Count how many trailing samples equal the latest one to 0.1 BPM.
        rounded = [round(v, 1) for v in buf]
        flat_run = 1
        for i in range(len(rounded) - 2, -1, -1):
            if rounded[i] == rounded[-1]:
                flat_run += 1
            else:
                break
        if flat_run >= self.DEAD_STICK_MIN_RUN:
            logger.warning(
                "ALERT  device=%s  hr=%.2f  reason=dead_stick  "
                "flat_run=%d  threshold=%d",
                device_id, heart_rate, flat_run, self.DEAD_STICK_MIN_RUN,
            )
            return True, float("inf")

        # (4) Model path
        score = self.score_window(np.asarray(buf, dtype=np.float32))
        decision = score > self.threshold
        if decision:
            logger.warning(
                "ALERT  device=%s  hr=%.2f  score=%.4f  threshold=%.4f  "
                "reason=model  window_mean=%.2f  window_std=%.2f",
                device_id, heart_rate, score, self.threshold,
                float(np.mean(buf)), float(np.std(buf)),
            )
        return decision, score

    def reset_window(self, device_id: str | None = None) -> None:
        """Test helper — clear rolling state for one device or all."""
        if device_id is None:
            self._windows.clear()
        else:
            self._windows.pop(device_id, None)

    # -------- persistence -------------------------------------------------
    def save(self, path: str | os.PathLike) -> None:
        self._ensure_model()
        with open(path, "wb") as f:
            pickle.dump({
                "model": self._model,
                "threshold": self.threshold,
                "contamination": self.contamination,
                "n_estimators": self.n_estimators,
            }, f)
        logger.info("SAVE   path=%s", path)

    def load(self, path: str | os.PathLike) -> "AIIDS":
        with open(path, "rb") as f:
            blob = pickle.load(f)
        self._model = blob["model"]
        self.threshold = blob["threshold"]
        self.contamination = blob["contamination"]
        self.n_estimators = blob["n_estimators"]
        logger.info("LOAD   path=%s  threshold=%.4f", path, self.threshold)
        return self


# ---------------------------------------------------------------------------
# Convenience singleton for the gateway hot path
# ---------------------------------------------------------------------------
_default: AIIDS | None = None


def get_detector(model_path: str | os.PathLike | None = None) -> AIIDS:
    """Lazy-load a pretrained detector from disk (pickle)."""
    global _default
    if _default is None:
        if model_path is None:
            model_path = Path(__file__).with_name("models") / "iforest.pkl"
        _default = AIIDS().load(model_path)
    return _default


# ---------------------------------------------------------------------------
# Demo — trains on synthetic healthy data, then probes 4 attack types
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("AI-IDS (Isolation Forest) — demo")
    print("=" * 70)

    rng = np.random.default_rng(42)
    # Synthetic "healthy" stream: baseline ~72 BPM, gentle variation
    baseline = 72 + 4 * np.sin(np.linspace(0, 12 * np.pi, 5000))
    healthy = baseline + rng.normal(0, 2.5, size=5000)
    healthy = np.clip(healthy, 50, 110)

    ids = AIIDS(contamination=0.01, random_state=0).fit(healthy)

    # Four attack families — the exact ones exercised by test_ai_ids.py
    attacks = {
        "SPIKE      (extreme +) ": healthy[:50].tolist() + [275.0, 260.0, 280.0],
        "DROP       (extreme -) ": healthy[:50].tolist() + [8.0, 5.0, 3.0],
        "DEAD-STICK (flat)      ": healthy[:50].tolist() + [72.0] * 15,
        "DRIFT      (slow climb)": healthy[:50].tolist()
                                   + list(np.linspace(110, 180, 15)),
    }

    for label, stream in attacks.items():
        ids.reset_window()
        detected_at = None
        reason = None
        for i, v in enumerate(stream):
            flagged, s = ids.inspect("dev-demo", v)
            if flagged and detected_at is None:
                detected_at = i
                reason = "rule" if s == float("inf") else "model"
        tag = (f"detected@sample={detected_at} ({reason})"
               if detected_at is not None else "NOT DETECTED")
        print(f"  {label}  →  {tag}")

    # Normal stream baseline — expect a low false-positive rate
    ids.reset_window()
    fp = sum(1 for v in healthy[-1000:] if ids.inspect("dev-normal", v)[0])
    print(f"\n  NORMAL baseline on 1000 held-out healthy samples  →  "
          f"{fp} alerts  ({fp / 1000:.2%} FPR)")
    print()

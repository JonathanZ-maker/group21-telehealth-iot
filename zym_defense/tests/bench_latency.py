"""
bench_latency.py
================
Latency benchmark for all four ZYM defence modules.

Measures the per-call overhead added to the gateway / cloud hot path
and produces the figure used in CW2 Report Page 4 (Trade-off section).

Method
------
For each module we time N=2000 calls with timeit, report mean ± std in
milliseconds, then render a grouped bar chart.

No network, no Flask, no MongoDB — all calls are pure-Python in-process,
which is the correct baseline for "overhead introduced by this defence
module" as opposed to overall HTTP round-trip latency.

Outputs
-------
  zym_defense/figures/latency_overhead.png   — bar chart (ms per call)
  zym_defense/tests/results/latency_ms.csv   — raw numbers for the report

Author: ZYM (Group 21)
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FIG_DIR = ROOT / "zym_defense" / "figures"
RESULTS_DIR = ROOT / "zym_defense" / "tests" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── benchmark helpers ─────────────────────────────────────────────────────────

def bench(fn, n: int = 2000) -> tuple[float, float]:
    """Return (mean_ms, std_ms) over n calls."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    arr = np.array(times)
    return float(arr.mean()), float(arr.std())


# ── set up callables ──────────────────────────────────────────────────────────

def setup_dp():
    from zym_defense.gateway_dp import LaplaceDP
    dp = LaplaceDP(epsilon=1.0, seed=0)
    return lambda: dp.privatise(75.0, reference=72.0)


def setup_ai_ids():
    import numpy as np
    from zym_defense.gateway_ai_ids import AIIDS, WINDOW

    rng = np.random.default_rng(0)
    healthy = np.clip(72 + rng.normal(0, 3, 6000), 50, 110)
    ids = AIIDS(contamination=0.01, random_state=0).fit(healthy)

    # Pre-warm the buffer with WINDOW-1 values so inspect() hits the model path
    dev = "bench-dev"
    for v in healthy[:WINDOW - 1]:
        ids.inspect(dev, float(v))

    return lambda: ids.inspect(dev, 74.0)


def setup_schema():
    """Benchmark the core validation logic without Flask."""
    from pydantic import ValidationError
    from zym_defense.cloud_schema import HeartRateRecord

    good = {"patient_id": "P001", "timestamp": 1713355200, "heart_rate": 78.5}
    return lambda: HeartRateRecord(**good)


def setup_schema_block():
    """Same but timing the rejection path (dict-valued field)."""
    from pydantic import ValidationError
    from zym_defense.cloud_schema import HeartRateRecord

    bad = {"patient_id": {"$ne": None}, "timestamp": 1713355200, "heart_rate": 78.5}

    def _call():
        try:
            HeartRateRecord(**bad)
        except ValidationError:
            pass

    return _call


def setup_auth():
    import os
    os.environ.setdefault("ZYM_JWT_SECRET", "bench-secret-000")
    from zym_defense.cloud_auth import issue_token, verify_token

    token = issue_token("bench-device", ["ingest:write"], ttl_seconds=3600)
    return lambda: verify_token(token)


# ── run and plot ──────────────────────────────────────────────────────────────

MODULES = [
    ("DP\n(privatise)", setup_dp),
    ("AI-IDS\n(inspect)", setup_ai_ids),
    ("Pydantic\n(allow)", setup_schema),
    ("Pydantic\n(block)", setup_schema_block),
    ("JWT\n(verify)", setup_auth),
]


def main() -> None:
    print("=" * 60)
    print("Latency benchmark — 2000 calls per module")
    print("=" * 60)

    results = []
    for label, setup_fn in MODULES:
        try:
            fn = setup_fn()
            mean_ms, std_ms = bench(fn)
            results.append((label, mean_ms, std_ms))
            clean_label = label.replace("\n", " ")
            print(f"  {clean_label:<22} {mean_ms:>7.3f} ± {std_ms:.3f} ms")
        except Exception as exc:
            print(f"  {label.replace(chr(10),' '):<22} SKIPPED ({exc})")
            results.append((label, 0.0, 0.0))

    # Save CSV
    csv_path = RESULTS_DIR / "latency_ms.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["module", "mean_ms", "std_ms"])
        for label, mean_ms, std_ms in results:
            w.writerow([label.replace("\n", " "), f"{mean_ms:.4f}", f"{std_ms:.4f}"])
    print(f"\nCSV → {csv_path}")

    # Plot
    labels = [r[0] for r in results]
    means  = [r[1] for r in results]
    stds   = [r[2] for r in results]

    colours = ["#4393c3", "#2166ac", "#92c5de", "#d6604d", "#f4a582"]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(labels))
    bars = ax.bar(x, means, yerr=stds, capsize=4, width=0.55,
                  color=colours[:len(labels)], alpha=0.88,
                  error_kw=dict(elinewidth=1.2, ecolor="black"))

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Latency per call (ms)")
    ax.set_title("Per-module Processing Overhead (mean ± std, n=2000)")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(means) * 1.45 if means else 1)

    for bar, mean_ms in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + max(means) * 0.02,
                f"{mean_ms:.3f} ms",
                ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    out = FIG_DIR / "latency_overhead.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Figure → {out}")


if __name__ == "__main__":
    main()

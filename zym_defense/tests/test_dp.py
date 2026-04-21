"""
test_dp.py
==========
Experiments for the Differential-Privacy module (gateway_dp.py).

Produces two figures used in CW2 Report Page 4:

  dp_privacy_utility.png   — time-series comparison of original vs
                             DP-perturbed heart-rate (ε = 1.0).
                             Demonstrates that individual readings are
                             obfuscated but the population trend is
                             preserved.

  dp_epsilon_sweep.png     — MAE as a function of ε ∈ {0.1,0.5,1,2,5,10}.
                             This is the core privacy–utility trade-off
                             figure cited in the CW2 Trade-offs section.

No external data required — synthetic heart-rate drawn from a sinusoidal
baseline + Gaussian noise, matching the profile used for AI-IDS training.

Author: ZYM (Group 21)
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from zym_defense.gateway_dp import LaplaceDP  # noqa: E402

FIG_DIR = ROOT / "zym_defense" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def make_stream(n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 6 * np.pi, n)
    signal = 72 + 5 * np.sin(t) + rng.normal(0, 2.0, size=n)
    return np.clip(signal, 50, 110)


# ── Figure 1: time-series comparison ─────────────────────────────────────────

def fig_privacy_utility() -> None:
    N = 120
    truth = make_stream(N, seed=1)
    reference = float(np.median(truth))

    eps = 1.0
    dp = LaplaceDP(epsilon=eps, seed=42)
    noisy = np.array([dp.privatise(v, reference=reference) for v in truth])

    mae = float(np.mean(np.abs(noisy - truth)))
    mean_err = float(np.mean(noisy) - np.mean(truth))

    fig, axes = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)

    # Top: raw vs noisy
    ax = axes[0]
    ax.plot(truth, lw=1.4, label="Original HR", color="#2c7bb6")
    ax.plot(noisy, lw=1.0, alpha=0.75, label=f"DP-perturbed (ε={eps})",
            color="#d7191c", linestyle="--")
    ax.set_ylabel("Heart rate (BPM)")
    ax.set_title("Differential Privacy — individual readings vs. population trend")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    ax.annotate(f"MAE = {mae:.1f} BPM", xy=(0.02, 0.08),
                xycoords="axes fraction", fontsize=8, color="gray")

    # Bottom: rolling mean (window=20) showing trend is preserved
    w = 20
    roll_truth = np.convolve(truth, np.ones(w)/w, mode='valid')
    roll_noisy = np.convolve(noisy, np.ones(w)/w, mode='valid')
    x = np.arange(w-1, N)
    ax2 = axes[1]
    ax2.plot(x, roll_truth, lw=1.8, label="Original 20-sample mean",
             color="#2c7bb6")
    ax2.plot(x, roll_noisy, lw=1.4, alpha=0.85,
             label=f"DP 20-sample mean (bias={mean_err:+.1f} BPM)",
             color="#d7191c", linestyle="--")
    ax2.set_xlabel("Sample index")
    ax2.set_ylabel("Rolling mean (BPM)")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.3)
    ax2.annotate("Population trend preserved despite per-reading noise",
                 xy=(0.02, 0.08), xycoords="axes fraction",
                 fontsize=8, color="#555")

    fig.tight_layout()
    out = FIG_DIR / "dp_privacy_utility.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"[dp] saved → {out}")


# ── Figure 2: ε sweep (privacy–utility trade-off) ────────────────────────────

def fig_epsilon_sweep() -> None:
    N = 2000
    truth = make_stream(N, seed=2)
    reference = float(np.median(truth))

    epsilons = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    maes, p95s = [], []

    for eps in epsilons:
        dp = LaplaceDP(epsilon=eps, seed=0)
        noisy = np.array([dp.privatise(v, reference=reference) for v in truth])
        err = np.abs(noisy - truth)
        maes.append(float(np.mean(err)))
        p95s.append(float(np.percentile(err, 95)))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = np.arange(len(epsilons))
    width = 0.35

    bars1 = ax.bar(x - width/2, maes, width, label="Mean Absolute Error (MAE)",
                   color="#4393c3", alpha=0.85)
    bars2 = ax.bar(x + width/2, p95s, width, label="95th-percentile error",
                   color="#d6604d", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([str(e) for e in epsilons])
    ax.set_xlabel("Privacy budget ε  (smaller = more private)")
    ax.set_ylabel("Error (BPM)")
    ax.set_title("DP Privacy–Utility Trade-off: MAE vs. ε")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Annotate each bar with its value
    for bar in list(bars1) + list(bars2):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.3,
                f"{h:.1f}", ha="center", va="bottom", fontsize=7)

    # Vertical line at chosen ε
    chosen_idx = epsilons.index(1.0)
    ax.axvline(x=chosen_idx, color="green", linestyle="--", lw=1.2,
               label="Chosen ε = 1.0")
    ax.legend(fontsize=8)

    fig.tight_layout()
    out = FIG_DIR / "dp_epsilon_sweep.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"[dp] saved → {out}")

    # Print summary table for the report
    print("\nε-sweep summary (copy into report Table):")
    print(f"{'ε':>6}  {'MAE':>8}  {'p95':>8}")
    for eps, mae, p95 in zip(epsilons, maes, p95s):
        marker = " ← chosen" if eps == 1.0 else ""
        print(f"{eps:>6}  {mae:>8.2f}  {p95:>8.2f}{marker}")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("DP experiments")
    print("=" * 60)
    fig_privacy_utility()
    fig_epsilon_sweep()
    print("\nDone. Both figures written to zym_defense/figures/")

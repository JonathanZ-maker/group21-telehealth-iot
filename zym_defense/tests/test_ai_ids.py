"""
test_ai_ids.py
==============
Rigorous evaluation of the AI-IDS module. Produces the figure used in
CW2 Report Page 4.

Design
------
We build a labelled test set by mixing:
  • 1000 benign rolling-windows drawn from held-out healthy heart-rate
    data (label = 0)
  • 1000 malicious rolling-windows synthesised from four attack families
    (label = 1):
        - spike      : inject an extreme positive value
        - drop       : inject an extreme negative value
        - dead-stick : overwrite with a constant value
        - drift      : slowly climbing trend

The detector is trained on a separate slice of healthy data that never
appears in the test set.

Outputs
-------
  zym_defense/figures/ai_ids_roc.png           — ROC curve + AUC
  zym_defense/figures/ai_ids_confusion.png     — confusion matrix at the
                                                 default threshold
  zym_defense/tests/results/ai_ids_metrics.csv — precision / recall / F1

These figures and numbers go directly into CW2 §4 "Experimental results".
"""

from __future__ import annotations
from zym_defense.gateway_ai_ids import AIIDS
import numpy as np

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")      # headless-safe for CI / server runs
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve)

# Make the script runnable from anywhere (`python -m zym_defense.tests.test_ai_ids`)
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from zym_defense.gateway_ai_ids import AIIDS, WINDOW, featurise_stream  # noqa: E402

FIG_DIR = ROOT / "zym_defense" / "figures"
RESULTS_DIR = ROOT / "zym_defense" / "tests" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Synthesise data
# ---------------------------------------------------------------------------
def make_healthy(n: int, rng: np.random.Generator) -> np.ndarray:
    """Sinusoidal baseline ≈72 BPM with Gaussian noise. Stays in [50, 110]."""
    t = np.linspace(0, 12 * np.pi, n)
    signal = 72 + 4 * np.sin(t) + rng.normal(0, 2.5, size=n)
    return np.clip(signal, 50, 110)


def make_attack_windows(healthy_tail: np.ndarray,
                        n_per_kind: int,
                        rng: np.random.Generator) -> np.ndarray:
    """
    Build attack windows by taking a healthy prefix of length WINDOW-k
    and appending k tampered samples of a given kind.

    The resulting windows have the same shape as benign ones but contain
    the adversarial perturbation at the trailing positions, mimicking a
    live attack observed through the streaming inspector.
    """
    windows = []
    stash = healthy_tail.copy()

    for _ in range(n_per_kind):
        idx = rng.integers(0, len(stash) - WINDOW)
        # SPIKE — one extreme positive value at the tail
        w = stash[idx:idx + WINDOW].copy()
        w[-1] = rng.uniform(230, 280)
        windows.append(w)

    for _ in range(n_per_kind):
        idx = rng.integers(0, len(stash) - WINDOW)
        # DROP — one extreme negative value at the tail
        w = stash[idx:idx + WINDOW].copy()
        w[-1] = rng.uniform(3, 25)
        windows.append(w)

    for _ in range(n_per_kind):
        idx = rng.integers(0, len(stash) - WINDOW)
        # DEAD-STICK — last 6 samples overwritten with a constant
        w = stash[idx:idx + WINDOW].copy()
        const = float(rng.uniform(65, 80))
        w[-6:] = const
        windows.append(w)

    for _ in range(n_per_kind):
        idx = rng.integers(0, len(stash) - WINDOW)
        # DRIFT — last 5 samples climb by +8 BPM / step
        w = stash[idx:idx + WINDOW].copy()
        start = w[-6]
        w[-5:] = start + np.arange(1, 6) * 8.0
        windows.append(w)

    return np.asarray(windows, dtype=np.float32)


# ---------------------------------------------------------------------------
# 2. Evaluate
# ---------------------------------------------------------------------------
def main() -> None:
    rng = np.random.default_rng(seed=2024)

    # Train set: first half of a large healthy stream
    train_healthy = make_healthy(n=6000, rng=rng)
    test_healthy = make_healthy(n=6000, rng=rng)   # fresh draw, disjoint

    print("[1/5] Training Isolation-Forest on 6000 healthy samples...")
    ids = AIIDS(contamination=0.01, random_state=0).fit(train_healthy)

    # Benign windows from held-out healthy data
    print("[2/5] Building test set (1000 benign + 1000 attack windows)...")
    benign_windows = featurise_stream(test_healthy)[:1000]
    benign_labels = np.zeros(len(benign_windows), dtype=int)

    # Attack windows — 250 of each of the 4 kinds = 1000 total
    attack_raw = make_attack_windows(test_healthy, n_per_kind=250, rng=rng)
    attack_windows = np.array([
        ids._ensure_model()  # warm-up sanity check
        or None  # noqa
        for _ in [0]
    ]) if False else None  # (purely to flush lazy load; ignore)
    from zym_defense.gateway_ai_ids import _featurise
    attack_windows = np.stack([_featurise(w) for w in attack_raw])
    attack_labels = np.ones(len(attack_windows), dtype=int)

    X = np.vstack([benign_windows, attack_windows])
    y = np.concatenate([benign_labels, attack_labels])

    # Score every window using the FULL hybrid-detector path: we feed the
    # last sample of each window through inspect() after priming the
    # rolling buffer with the first WINDOW-1 samples. This matches how
    # the gateway actually uses the detector in production.
    print("[3/5] Scoring via full inspect() path (rule + model)...")
    scores = np.empty(len(X), dtype=np.float64)
    y_pred = np.zeros(len(X), dtype=int)

    all_raw_windows = np.vstack([
        test_healthy[np.arange(1000)[:, None] + np.arange(WINDOW)],  # benign raw
        attack_raw,                                                   # attack raw
    ])

    for i, raw_win in enumerate(all_raw_windows):
        # Use a unique device id per sample so rolling state is fresh
        dev = f"eval-{i}"
        # Prime the window with the first WINDOW-1 readings (no alerts
        # can fire yet because len(buf) < WINDOW).
        for v in raw_win[:-1]:
            ids.inspect(dev, float(v))
        # Final reading fires the decision
        flagged, s = ids.inspect(dev, float(raw_win[-1]))
        scores[i] = s
        y_pred[i] = int(flagged)

    # For ROC we need numeric scores; replace +inf with a large finite
    # value equal to twice the largest finite score.
    finite_max = scores[np.isfinite(scores)].max()
    scores_for_roc = np.where(np.isinf(scores), finite_max * 2, scores)

    # ---------------------------------------------------------------
    # 3. Metrics
    # ---------------------------------------------------------------
    auc = roc_auc_score(y, scores_for_roc)
    prec = precision_score(y, y_pred)
    rec = recall_score(y, y_pred)
    f1 = f1_score(y, y_pred)
    cm = confusion_matrix(y, y_pred)

    # Per-attack-type breakdown
    print("[4/5] Per-attack-type recall:")
    breakdown = {}
    for i, kind in enumerate(["spike", "drop", "dead-stick", "drift"]):
        mask = np.zeros(len(y), dtype=bool)
        mask[1000 + i * 250:1000 + (i + 1) * 250] = True
        rec_k = y_pred[mask].mean()
        breakdown[kind] = rec_k
        print(f"  {kind:<12} recall = {rec_k:.3f}   (n={mask.sum()})")

    # Save CSV
    csv_path = RESULTS_DIR / "ai_ids_metrics.csv"
    with open(csv_path, "w") as f:
        f.write("metric,value\n")
        f.write(f"auc,{auc:.4f}\n")
        f.write(f"precision,{prec:.4f}\n")
        f.write(f"recall,{rec:.4f}\n")
        f.write(f"f1,{f1:.4f}\n")
        f.write(f"threshold,{ids.threshold:.4f}\n")
        f.write(f"fpr,{cm[0,1]/cm[0].sum():.4f}\n")
        for k, v in breakdown.items():
            f.write(f"recall_{k},{v:.4f}\n")

    # ---------------------------------------------------------------
    # 4. ROC figure
    # ---------------------------------------------------------------
    print("[5/5] Rendering figures...")
    fig, ax = plt.subplots(figsize=(6, 5.2))
    fpr, tpr, _ = roc_curve(y, scores_for_roc)
    ax.plot(fpr, tpr, lw=2.2, label=f"AI-IDS (AUC = {auc:.3f})")
    ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="Random")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("AI-IDS — Isolation Forest, hybrid rule + model")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "ai_ids_roc.png", dpi=160)
    plt.close(fig)

    # ---------------------------------------------------------------
    # 5. Confusion-matrix figure
    # ---------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(4.2, 3.8))
    im = ax.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        color = "white" if v > cm.max() / 2 else "black"
        ax.text(j, i, str(v), ha="center", va="center", color=color, fontsize=13)
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Benign", "Attack"])
    ax.set_yticklabels(["Benign", "Attack"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"Confusion matrix (τ = {ids.threshold:.3f})")
    fig.colorbar(im, ax=ax, shrink=0.75)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "ai_ids_confusion.png", dpi=160)
    plt.close(fig)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"AUC           = {auc:.4f}")
    print(f"Precision     = {prec:.4f}")
    print(f"Recall (TPR)  = {rec:.4f}")
    print(f"F1            = {f1:.4f}")
    print(f"FPR           = {cm[0,1]/cm[0].sum():.4f}")
    print(f"Threshold     = {ids.threshold:.4f}")
    print("=" * 60)
    print(f"\nFigures  → {FIG_DIR}/ai_ids_roc.png  and  ai_ids_confusion.png")
    print(f"Metrics  → {csv_path}")
    
    rng = np.random.default_rng(2024)
    t = np.linspace(0, 12 * np.pi, 6000)
    healthy = np.clip(72 + 4*np.sin(t) + rng.normal(0, 2.5, 6000), 50, 110)
    ids = AIIDS(contamination=0.01, random_state=0).fit(healthy)
    ids.save("zym_defense/models/iforest.pkl")

if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# run_experiments.sh — reproduce every figure in the CW2 report.
#
# After this finishes, `zym_defense/figures/` holds:
#   - ai_ids_roc.png          (AI-IDS detection performance)
#   - dp_privacy_utility.png  (original vs noisy heart-rate time series)
#   - dp_epsilon_sweep.png    (MAE as a function of ε)
#   - latency_overhead.png    (per-module latency bars)
#
# and `zym_defense/tests/results/` holds raw CSVs for each experiment.

set -e
cd "$(dirname "$0")/.."

mkdir -p zym_defense/figures zym_defense/tests/results

echo "=== AI-IDS: train + ROC ==="
python -m zym_defense.tests.test_ai_ids

echo "=== DP: privacy-utility ==="
python -m zym_defense.tests.test_dp

echo "=== Cloud schema: injection tests ==="
python -m zym_defense.tests.test_schema

echo "=== JWT auth: access-control tests ==="
python -m zym_defense.tests.test_auth

echo "=== Latency overhead benchmark ==="
python -m zym_defense.tests.bench_latency

echo "All experiments complete. Figures in zym_defense/figures/"
ls -1 zym_defense/figures/

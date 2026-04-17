# `zym_defense/tests/` — Experimental scripts

Each script in this folder does two things:

1. **Validates** that a defence module behaves correctly against adversarial inputs (unit-test role).
2. **Produces** one or more figures consumed by the CW2 report (experimental-evaluation role).

## Planned scripts (to be created)

| Script | Module under test | Output figure(s) | Consumed by |
|--------|-------------------|------------------|-------------|
| `test_schema.py` | `cloud_schema.py` | none (pass/fail table printed) | CW2 p.3 screenshot |
| `test_auth.py` | `cloud_auth.py` | none (pass/fail table printed) | CW2 p.3 screenshot |
| `test_dp.py` | `gateway_dp.py` | `dp_privacy_utility.png`, `dp_epsilon_sweep.png` | CW2 p.4 |
| `test_ai_ids.py` | `gateway_ai_ids.py` | `ai_ids_roc.png`, `ai_ids_confusion.png` | CW2 p.4 |
| `bench_latency.py` | all four | `latency_overhead.png`, `latency_table.csv` | CW2 p.4 |

## How to run

```bash
# from repo root
python -m zym_defense.tests.test_schema
python -m zym_defense.tests.test_auth
python -m zym_defense.tests.test_dp
python -m zym_defense.tests.test_ai_ids
python -m zym_defense.tests.bench_latency

# or everything at once
bash scripts/run_experiments.sh
```

Figures are written to `zym_defense/figures/` and then copied to
`report/figures/` by the report build step.

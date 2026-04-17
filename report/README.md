# Report — `/report`

Final deliverables go here.

## Contents

| File | Owner | Description |
|------|-------|-------------|
| `CW1.pdf` | all | Coursework 1, 5 pages (threat modelling + attacks). Built from `CW1.tex` or `CW1.md`. |
| `CW2.pdf` | all | Coursework 2, 5 pages (defences + compliance). Built from `CW2.tex` or `CW2.md`. |
| `combined.pdf` | editor (volunteer) | The single 10-page PDF that actually gets submitted to Moodle. |
| `figures/` | authors of each module | All images referenced from the report. Keep filenames stable so `\includegraphics{figures/xyz}` does not break. |
| `individual_contributions.md` | each member writes their own paragraph | ≤200 words each (see assignment template). |

## Build

If we use LaTeX with the UCL template from Moodle:
```bash
cd report
latexmk -pdf CW1.tex
latexmk -pdf CW2.tex
```

If we use Markdown + Pandoc instead:
```bash
pandoc -o CW1.pdf CW1.md --template=ucl.tex
```

## Figures checklist (filled as modules complete)

- [ ] `figures/architecture.png` — end-to-end system diagram (CW1 p.1 + CW2 p.1)
- [ ] `figures/attack1_chain.png` — BLE attack chain (CW1 p.4)
- [ ] `figures/attack2_chain.png` — NoSQL attack chain (CW1 p.5)
- [ ] `figures/risk_matrix.png` — 2×2 risk matrix (CW1 p.3)
- [ ] `figures/ai_ids_roc.png` — produced by `zym_defense/tests/test_ai_ids.py` (CW2 p.4)
- [ ] `figures/dp_privacy_utility.png` — produced by `zym_defense/tests/test_dp.py` (CW2 p.4)
- [ ] `figures/dp_epsilon_sweep.png` — produced by `zym_defense/tests/test_dp.py` (CW2 p.4)
- [ ] `figures/latency_overhead.png` — produced by `zym_defense/tests/bench_latency.py` (CW2 p.4)
- [ ] Screenshot: HMAC blocking tampered packet (CW2 p.2)
- [ ] Screenshot: AI-IDS alert log (CW2 p.2)
- [ ] Screenshot: Pydantic 400 on injection (CW2 p.3)
- [ ] Screenshot: JWT 401 on unauthorised access (CW2 p.3)

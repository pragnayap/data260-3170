# METRICS — Non-Determinism Experiment (Part 3)

**Model:** qwen3:8b (reasoning disabled) via Ollama
**Fixed input:** `reports/hw01/cases/nondeterminism_input.json`
**Runs:** 20 per temperature, 40 total

## Tag Stability

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Distinct tag sets | 5 | 1 |
| Tags in all 20 runs | (none) | emergency response, public transportation, traffic incident |
| Tags in exactly 1 run | emergency assistance, public transportation, traffic incident | (none) |

## Latency (ms)

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| p50 | 76,921.5 | 72,597.0 |
| p95 | 82,781.4 | 73,167.2 |
| p99 | 82,985.9 | 80,603.8 |

## Source data

- Raw per-run results (all 40 runs): `reports/hw01/raw/nondeterminism_raw.json`, `nondeterminism_raw.csv`
- Computed summary: `reports/hw01/raw/nondeterminism_summary.json`
- Full console transcript: `reports/hw01/RUN_LOG.txt`

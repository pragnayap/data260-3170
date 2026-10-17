# HW6 METRICS

Model: qwen3:8b via Ollama, CPU only (Intel Core i9-9880H). Same 30-message conversation + 5 probes per setting, fresh user/session each. Raw per-turn data: `raw/turns_<label>.csv`; probe replies and scores: `raw/probe_scores_<label>.json`. Means are over the 30 conversation turns (probe turns excluded). Latency is the user-facing chat call (embedding + retrieval + model); episode extraction and summarization run after the reply and are reported as overhead.

## Part 3.3 / 3.4 - memory size and eviction policy

| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |
|---|---|---|---|
| SHORT_TERM_N=4 | 527 | 23303 | 5.00 |
| SHORT_TERM_N=12 | 797 | 49469 | 5.00 |
| SHORT_TERM_N=30 | 1193 | 61775 | 5.00 |
| Eviction policy (N=30 + evict_old_assistant) | 747 | 31912 | 5.00 |

Eviction vs plain N=30: prompt tokens/turn 1193 -> 747 (37.4% saved); probe quality 5.00 -> 5.00 (+0.00); latency 61775 -> 31912 ms.

### Where the prompt tokens go (mean per turn; proportional estimate, sums to the reported prompt tokens)

| Setting | System primer | Long-term summary | Short-term window | Episodic facts | Current msg | Completion |
|---|---|---|---|---|---|---|
| SHORT_TERM_N=4 | 86 | 228 | 148 | 48 | 16 | 55 |
| SHORT_TERM_N=12 | 89 | 260 | 383 | 49 | 17 | 51 |
| SHORT_TERM_N=30 | 91 | 242 | 792 | 51 | 17 | 50 |
| Eviction policy (N=30 + evict_old_assistant) | 85 | 299 | 300 | 47 | 16 | 58 |

### Probe scores by question

| Probe | SHORT_TERM_N=4 | SHORT_TERM_N=12 | SHORT_TERM_N=30 | Eviction policy (N=30 + evict_old_assistant) |
|---|---|---|---|---|
| P1_route | 5.0 | 5.0 | 5.0 | 5.0 |
| P2_identity | 5.0 | 5.0 | 5.0 | 5.0 |
| P3_equipment | 5.0 | 5.0 | 5.0 | 5.0 |
| P4_past_incident | 5.0 | 5.0 | 5.0 | 5.0 |
| P5_contact | 5.0 | 5.0 | 5.0 | 5.0 |

## Part 3.5 - memory cost, 10,000 conversations x 30 turns

Pricing: $1/M input tokens, $5/M output tokens. Token counts are the measured sums over the 30 turns. 'Chat only' counts the main reply call; 'All-in' also counts the extra model calls memory needs (episode extraction every turn, summaries every 6th user message).

| Setting | Input tok/conv | Output tok/conv | Chat-only cost | All-in input tok | All-in output tok | **All-in cost (10,000 conv)** | Probe |
|---|---|---|---|---|---|---|---|
| SHORT_TERM_N=4 | 15804 | 1646 | $240.34 | 23522 | 3437 | **$407.07** | 5.00 |
| SHORT_TERM_N=12 | 23922 | 1522 | $315.32 | 31735 | 3597 | **$497.20** | 5.00 |
| SHORT_TERM_N=30 | 35800 | 1513 | $433.65 | 43371 | 3386 | **$603.01** | 5.00 |
| Eviction policy (N=30 + evict_old_assistant) | 22398 | 1746 | $311.28 | 30678 | 4134 | **$513.48** | 5.00 |

**Worst setting** = highest all-in cost: SHORT_TERM_N=30 ($603.01).
**Best setting** = cheapest all-in cost among settings whose probe quality is within 0.5 of the best score (5.00): SHORT_TERM_N=4 ($407.07).
Cost ratio worst/best: 1.48x. Selecting by cost alone would ignore quality loss, so 'best' is the cheapest setting that has not given up recall.

## Part 4.5 - consolidation of the 55-line MEMORY.md

Lines before/after: 55 -> 35 (under 40: True); archived facts: 20; merge groups: 10; contradictions resolved: 25.

| Contradiction | Expected | Consolidator kept | Correct? |
|---|---|---|---|
| C1_backend_port | a | a | yes |
| C2_vite_port | b | b | yes |
| C3_mongo_install | b | b | yes |
| C4_secrets | b | b | yes |
| C5_secure_cookie | both | b | **NO** |

Resolved incorrectly: C5_secure_cookie.

## Part 4.4 - generated function vs AGENT.md

| Run | Attempt | Passed | Failed checks |
|---|---|---|---|
| with_agent_md | 1 | 7/9 | has_test_function, tests_pass |
| with_agent_md | 2 | 8/9 | tests_pass |
| with_agent_md | 3 | 8/9 | tests_pass |
| control_without_agent_md | 1 | 6/9 | docstring, has_test_function, tests_pass |
| control_without_agent_md | 2 | 8/9 | line_length_100 |
| control_without_agent_md | 3 | 7/9 | line_length_100, tests_pass |

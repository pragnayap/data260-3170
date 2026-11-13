# AI_USE — HW10

## 1. What did you use an AI assistant for, and what did you do yourself?

- I independently implemented, integrated, and tested the code in this submission, including the tracing module, HW8 agent changes, cache-first ingress, message collector, DeepEval judge wrapper, evaluator, judge-validation scripts, latency and trace-example scripts, Streamlit dashboard, and verification script.
- I used Claude Code from Anthropic only as a reference and verification tool. I consulted it to cross-check implementation decisions, validate debugging approaches, review whether the tests covered the assignment requirements, and confirm that the reported metrics were calculated correctly. I made the final implementation decisions, ran the experiments, reviewed the outputs, traces, logs, and dashboard, and decided what to report.
- I hand-assigned all 20 human labels myself before any judge scores were generated. I committed the labels first, and the validation process confirms that they existed before the judge output.


## 2. One AI-produced output that was wrong or unsuitable, or one thing I independently verified

- During the initial implementation review, the agent-stop process appeared to stop the launcher but left Python worker processes running. As a result, stale stub-mode agents continued consuming messages.
- I detected this by checking the generated drafts for stub text and noticing implausibly short latency values. I found the problem before assigning labels or generating judge scores. I fixed the process-cleanup logic so that it terminates the complete process tree, and I added a check that prevents the system from starting when stale agents are still running.


## 3. How did you detect the problem or verify the result?

- I ran make verify-hw10. This command recomputes the stage table from the raw spans and verifies that all 50 requests are confirmed cache misses with complete traces. It also checks that the evaluator arithmetic is consistent, that the human labels were committed before judge output, and that Spearman correlation, mean absolute difference, and repeatability are recomputed correctly from the raw per-case scores.
- I also manually read the drafts, logs, and traces, reviewed the dashboard pages, and checked the three example traces to confirm that the reported results matched the underlying evidence.


## 4. What did you change, and why does it work now?

- I fixed the process-cleanup logic, added a Planner retry with a clear failed result, pinned compatible dependency versions, and recaptured the cache-hit example after the system was warmed up.
- I also reran evaluations that initially lacked complete tracing and strengthened the verification script so that it checks the raw spans, labels.

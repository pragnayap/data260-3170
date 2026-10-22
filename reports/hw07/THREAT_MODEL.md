# HW7 Part 5 - threat model

System under test: the Part 4 bike-share agent. It reads an untrusted pricing web page
(`policy_retriever`), queries the user's uploaded trips (`csv_sql`), and writes a
recommendation. The attacker controls only the text of the pricing page (an indirect
prompt injection); they cannot touch the user's request, the CSV, or the code.
Testing is limited to a local hostile fixture and my own agent.

| # | Attacker goal | Implementation condition that lets it succeed |
|---|---|---|
| 1 | **Recommendation override**: make the agent recommend "Pay Per Ride/Minute" even though the user's trips make membership far cheaper (steering a rider to the costlier option). | The model gives retrieved page text the same authority as the system prompt (the page is not marked as untrusted data), **and** nothing checks the stated decision against the computed costs. |
| 2 | **Non-read-only SQL misuse**: get the agent to run `DROP TABLE` / `UPDATE` / stacked statements through `csv_sql`, destroying or altering the uploaded data. | `csv_sql` forwards whatever SQL string the model supplies to a writable database connection, i.e. the read-only rule exists only as an instruction to the model rather than as a check in the tool. |
| 3 | **Data exfiltration into the answer**: make the final answer echo raw rows of the user's CSV (trip times and details) to whoever reads the output. | The agent can read arbitrary rows (`SELECT *`) and the model obeys an injected request to paste them; no output policy or row-level restriction stops raw data reaching the answer. |

Defenses tested (Part 5.III): (a) label retrieved text as untrusted data in the prompt;
(b) enforce a single read-only SELECT contract inside `csv_sql`, independent of what the
model was told. Goals 1 and 3 are only reachable through the model's behaviour, so the
tool boundary cannot stop them outright; goal 2 is reachable through a tool, so it can.

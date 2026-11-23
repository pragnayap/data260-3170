# AI_USE — HW11

## 1. What did you use an AI assistant for, and what did you do yourself?

I completed the implementation, testing, fixtures, golden cases, policy, `watch.py` changes, verification, metrics, and report for HW11 myself. I used Claude Code mainly as a second check to validate my work, cross-check the requirements, review the test cases, and verify that my results and report were consistent with the assignment.

I reviewed and committed the policy and golden-set labels before running the agent. I also performed all the Muse steps myself, including installation, setting the standing instructions, scheduling, crash/restart testing, duplicate and retry testing, the injection test, metrics collection, usage readings, and the live run. I reviewed the traces and outputs, took the required screenshots, and decided what results and limitations to include in the report.

## 2. One AI-produced output that was wrong or unsuitable, or one thing I independently verified

I used Claude Code to cross-check my fixtures and test cases. During this review, I found that the 8-K fixture titles needed the ticker prefix to correctly match the golden `match_title` values. I verified this using the real tool and checked each golden case against the retrieved fixture items before running the agent.

I also independently tested the live Stooq price source and found that it was returning a JavaScript bot-check page instead of valid price data. I confirmed the same issue during the live Muse run, where all four tickers produced errors and SEC EDGAR returned HTTP 400.

During the live run, I also noticed that Muse summarized the result as "0 new, no candidates" without mentioning the source errors required by the standing instructions. I checked the trace and confirmed that the source errors were present even though they were missing from the summary.

## 3. How did you detect the problem or verify the result?

I used `make verify-hw11` and Claude Code as an additional cross-check to validate my results. I verified that the golden set contained 12 cases with two cases per category, and that the policy, fixtures, and labels were committed before the first Muse run.

I also checked that all golden cases resolved correctly against the fixtures, producing 11 candidates and 1 duplicate, matching the Muse results. I verified the injection tests, confirmed that the kit's original demo still passed after my `watch.py` changes, and checked that non-CSV responses were correctly recorded as source errors.

Finally, I manually compared the trace, metrics, screenshots, and live-run output with the report to make sure the reported results were accurate. The Muse metrics showed 12 out of 12 correct decisions.

## 4. What did you change, and why does it work now?

I updated `watch.py` so that a non-CSV price response is logged as a `source_error` instead of being treated like a normal day with no price movement. I also added a per-ticker candidate floor so that small movements in volatile stocks do not unnecessarily reach the agent. I fixed the fixture titles so they correctly match the golden cases.

After making these changes, I reran the tests and verification and used Claude Code to cross-check the implementation and results for any inconsistencies.

The remaining limitations are also documented in my report. The live Stooq and EDGAR sources still fail on Muse, the summary does not properly include source errors, the 12 hand-designed cases provide limited evidence even though they all passed, restart recovery was tested only once, Muse's token usage is only an estimate based on percentage usage, and the price thresholds are based on approximate judgments rather than measured historical values.
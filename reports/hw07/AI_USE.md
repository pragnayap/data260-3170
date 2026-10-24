AI_USE — HW7
1. What did you use an AI assistant for, and what did you do yourself?
I used an AI assistant strictly for high-level ideation, initial boilerplate code generation, and assisting with execution monitoring during long-running tests. I consulted AI during initial technical discussions on JWT authentication mechanics, agent-loop patterns, Reflexion architecture, ReAct/MRKL data pipelines, prompt-injection defense strategies, and file-tool security gating.

I personally designed and authored the application logic and codebase. I established all core architectural parameters—including selecting the target city, establishing the official monthly-price assumptions, choosing real public datasets over synthetic ones, defining verification test cases, and implementing logic fixes. I wrote, refactored, and integrated the core modules into the project repository, executed and debugged all local test suites, captured validation screenshots, analyzed system execution logs, and authored the final technical report.

Every line of system behavior and code output was evaluated and verified by me against the assignment requirements. I personally authored and updated test checks for authentication/authorization workflows, tool-calling loops, public-data cost formulas, prompt-injection resilience, and the ten-command safety gate. AI suggestions were treated merely as preliminary drafts; I revised, debugged, rewritten, or discarded them whenever they failed to conform to the required specifications.

2. One AI-produced output that was wrong or unsuitable, or one thing I independently verified
The original verifier script for Task-B was fundamentally broken: it incorrectly passed runs even when the agent explicitly reported that no supporting example incident had been retrieved. This produced false positives, falsely inflating accuracy to 7/7 and 20/20 despite failing the underlying requirement.

In Part 4, initial code implementations introduced an invalid pricing constant of $300 that was completely unsupported by official public pricing documentation, producing faulty cost-comparison calculations.

In Part 6, the initial safety gate implementation contained a severe logic flaw that resulted in four false allows. Destructive system commands were allowed through because they partially matched entries in an unconstrained prefix allow-list. Additionally, the scripted replay for injected SQL required manual code-level inspection to verify that the database restrictions were enforced by the tool boundary rather than resting on soft prompt-level model compliance.

3. How did you detect the problem or verify the result?
I detected the Task-B flaw through hands-on code inspection and screenshot auditing. Noticing that execution transcripts explicitly stated no incident was found, I inspected the verifier source code and execution logs across all seven test runs to confirm the systemic logic error. I wrote mock unit tests to isolate the bug and validated the fix before re-running the benchmark.

I caught the Part 4 pricing error during independent mathematical recomputation and code review. Comparing hardcoded price values in the scripts against verified pricing page assets revealed that the $300 figure was completely ungrounded.

For Part 6, I probed the safety gate programmatically using a custom test suite of safe and destructive commands. The execution traces exposed four false allows in the initial implementation. I cross-referenced this with the system design contract: destructive commands must be intercepted by an explicit evaluation pass before any prefix allow-list check can execute.

I audited raw log files, execution traces, system outputs, and verifier scripts directly rather than relying on top-level status codes. This ensured that task completions represented genuine programmatic success rather than hallucinated or malformed answers.

4. What did you change, and why does it work now?
I refactored the Task-B verification logic to enforce dual-condition checks requiring both the aggregate output and an independently validated example incident. I updated the system prompts and search logic accordingly, tested three prompt/code variants, and re-executed the evaluation pipeline.

I updated the Part 4 codebase to bind all cost calculations dynamically to verified pricing evidence files. I isolated earlier invalid runs in the project history log and updated the final analysis to reflect accurate data.

For Part 3, I modified the Task-C verifier code to loosen over-rigid string-matching constraints while preserving rigorous validation of required search and detail-lookup sequences. Rerunning the updated pipeline yielded a reliable score of 20/20 task completions and 66/66 well-formed tool calls.

For Part 6, I completely restructured the safety gate architecture. I modified the command execution pipeline so that an independent destructive-command parser executes prior to the SAFE_PREFIXES allow-list filter. Commands involving recursive deletion (rm -rf), privilege escalation (sudo/su), ownership modifications (chmod/chown), raw device writes, or protected system paths now strictly trigger explicit confirmation checks or immediate blocks.

The final repository reflects fully corrected code implementations, clean test suites yielding 20/20 and 66/66 outcomes, preserved historical run logs, and open disclosure of all remaining system trade-offs and verifier boundaries.
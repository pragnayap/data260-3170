# AI Use Statement

**1. What I used an AI assistant for, and what I did myself**

I used Claude Code (Sonnet 5.5) as a reference and guidance tool while completing HW9. I used it to clarify concepts, discuss possible implementation approaches, troubleshoot errors, and review parts of my work. I wrote and integrated the Redis view-counter method in `cache_db.py`, the RediSearch-based semantic cache in `semantic_cache.py`, the database-grounded Q&A agent in `qa_agent.py`, the threshold-sweep, stale-answer, Part 4, and verification scripts, and this final write-up.

I made the design decisions, selected the required constraints and labels, implemented the solution, ran the experiments, checked the outputs, and interpreted the results myself.

**2. One AI suggestion that was unsuitable, and what I independently verified**

- Homebrew Redis was already installed, but it did not include the required search module. I verified this using `MODULE LIST`, saw that only the `vectorset` module was available, and switched to the `redis/redis-stack-server` Docker image so that vector indexing could work.
- The first counter test printed “Synced views to database” inside the method, which caused the output order to differ from the handout. I identified the issue and moved the print statement to the test script.
- The first Part 4 test set included a question about “Route 128,” which was not present in `reference_dataset.json`. I checked the dataset, identified the problem, and changed the question before running the evaluation.
- I independently checked the ten different-answer near-miss labels against MySQL before running the sweep.
- I also verified the sweep results by recomputing the hit and false-hit counts from the raw results.

**3. How I verified the implementation and results**

I ran `verify_hw09.py` to verify the complete implementation. The verification checked that:

- The sweep results were recomputed from the raw per-case data.
- `cache_cases.yaml` was committed before the sweep output was generated and was not modified afterward.
- The view counter worked through 25 accesses using the real Redis and MySQL services.
- A stale cached answer was evicted after the corresponding route record was updated.
- The Part 4 input files contained only questions.
- No test question appeared in the training data or in any lesson.

I also reviewed the generated outputs and checked that the results matched the expected behavior.

**4. What I changed and why it works**

I corrected the Redis setup, fixed the counter test output order, replaced the invalid Part 4 question, and verified the results using the actual Redis and MySQL services. These changes ensure that the implementation follows the assignment requirements and that the reported results are based on reproducible checks.

The following limitations are stated clearly:

- The sweep’s miss latency is the mean of 20 measured agent runs, rather than a new agent run for every individual miss.
- The near-miss false hits are not eliminated simply by increasing the similarity threshold.
- The Part 4 evaluator is rule-based rather than an LLM judge.
- The broad candidate lesson in Part 4.III was intentionally written by hand to test the filtering gate.
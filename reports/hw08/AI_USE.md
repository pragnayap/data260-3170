# AI_USE — HW8

AI Use

## 1. What did you use an AI assistant for, and what did you do yourself?

I completed the implementation, testing, debugging, and verification for this assignment myself. I used Claude as a reference when I needed help understanding Kafka consumer behavior, idempotency handling, retry logic, partition offsets, interpreting error messages, and making a few minor fixes. Claude provided suggestions and explanations, but I wrote and integrated the code, made the design decisions, ran the experiments, investigated the failures, and verified the final results myself.

I independently analyzed the duplicate-delivery problem, identified the race condition caused by the shared temporary state file, changed the Writer state to an append-only log, adjusted the retry and bookkeeping order, corrected the test harness's start-offset and partition handling, investigated the failed verification runs, and confirmed the final results using two consecutive full runs and make verify-hw08.

## 2. One AI-produced output that was wrong or unsuitable, or one thing I independently verified

The first version of my Writer, created with some AI assistance, stored its idempotency state in one JSON file and rewrote it through a shared temporary filename. When I ran two Writers in the same consumer group, they competed for that file, and one process failed with an ENOENT error. The retry loop then repeated the entire message, causing the draft to be delivered twice. This exposed the duplicate-delivery problem addressed in Part 3.

I also found problems in the first versions of my failure tests. The "ready" message was printed before the consumer had fixed its starting offset, and the poison and death tests were sending messages to incorrect partitions.

## 3. How did you detect the problem or verify the result?

I detected the main problem by examining the ordering-test results. Although 20 messages were sent, the test processed 21 messages. The processing log showed that the same partition and offset had been handled twice, with a RETRY caused by [Errno 2] immediately beforehand.

I also inspected the failed death and poison test runs and found that no offset had been committed in the consumer-group table. While retaking the screenshots, I received additional FAIL results. I investigated the running processes and found two Writer processes left over from an interrupted run. After stopping those processes, I reran the tests and confirmed that they passed. I kept the earlier failed runs in raw/dev_history/ for comparison and documentation.

## 4. What did you change, and why does it work now?

I changed the Writer's idempotency state from a shared rewritten JSON file to an append-only log containing one correlation_id per line. This allows multiple Writer instances to share the state more safely without racing over one temporary file.

I also changed the retry structure so that retries cover only the processing work and draft delivery. The bookkeeping is performed afterward, which prevents the entire message from being unnecessarily repeated because of a state-file error.

For the test harness, I made it establish the starting offsets before printing "ready" and ensured that related test messages are sent to the same partition. I then ran all four scenarios twice consecutively and confirmed that both full runs passed. The final verification command, make verify-hw08, passed all 16 of 16 checks.

The remaining limitations are that the tests use stub drafts, Kafka runs with a single broker, and delivery is at-least-once. Therefore, a crash occurring after draft delivery but before the delivery is recorded could still result in one duplicate.

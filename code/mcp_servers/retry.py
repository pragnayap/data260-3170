"""
HW5 Part 3 - timeouts and a bounded exponential-backoff retry policy.

The spec asks for retries around "API or storage operations that may fail",
and for three behaviours to be demonstrated:

    1. success on the first attempt
    2. failure on the first attempt followed by success after a retry
    3. failure after all allowed retries, returning a clean error result
       instead of crashing

All three are produced by `make retry-demo` (fault_injection.py --demo).

Two design decisions worth defending in the demo:

RETRY ONLY WHAT CAN SUCCEED LATER.
    A dropped connection or a timeout may well work on the next attempt, so
    those are retried. A rejected argument -- `limit=0`, a malformed incident
    code -- will be rejected identically every time, so it is returned
    immediately. Retrying a validation failure spends three times the latency
    to produce the same answer. The split is mechanical: a transient fault
    raises TransientError, while a rejection comes back as an ok=False
    envelope from the tool itself.

BOUNDED MEANS TWO CEILINGS, NOT ONE.
    The delay doubles (base, base*2, base*4 ...) but is capped at max_delay,
    and the number of attempts is capped at max_attempts. Without the first
    cap a long retry chain ends up sleeping for minutes; without the second
    it never ends at all. "Bounded exponential backoff" is both.

Nothing here raises past its own boundary: call_with_retry always returns an
envelope, which is what lets the Part 5 agent loop survive a failing tool.
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from envelope import Envelope, err, is_envelope

log = logging.getLogger("transit-mcp.retry")


class TransientError(Exception):
    """A failure that might not recur: a dropped call, a timeout, a 503.

    This is the only exception call_with_retry retries. Everything else is
    either a bug (which should surface) or a rejection (which the tool
    already expressed as an ok=False envelope).
    """


# --- policy ----------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Interactive defaults. Part 3's written answer argues for different
    numbers in a batch context; see BATCH_POLICY at the bottom of this file."""

    max_attempts: int = 3        # 1 initial call + 2 retries
    base_delay_s: float = 0.05   # first backoff
    max_delay_s: float = 0.40    # ceiling on any single backoff
    timeout_s: float = 2.00      # per-attempt, not per-call
    jitter: bool = True          # spread retries so they do not synchronize

    def delay_for(self, attempt: int, rng: random.Random | None = None) -> float:
        """Backoff before attempt N+1, in seconds.

        attempt is 1-based, so the wait after the first failure uses
        base_delay * 2**0 = base_delay.
        """
        raw = self.base_delay_s * (2 ** (attempt - 1))
        capped = min(raw, self.max_delay_s)
        if self.jitter and rng is not None:
            # Full jitter: sleep a random amount up to the capped delay. With
            # many clients this stops them all retrying on the same tick.
            return rng.uniform(0.0, capped)
        return capped


# The numbers Part 3's written answer recommends for batch processing, kept
# here as code so the report's claim is checkable rather than rhetorical.
INTERACTIVE_POLICY = RetryPolicy()
BATCH_POLICY = RetryPolicy(
    max_attempts=6,
    base_delay_s=0.50,
    max_delay_s=30.0,
    timeout_s=60.0,
    jitter=True,
)


# --- per-attempt and per-call records --------------------------------------

@dataclass
class Attempt:
    number: int
    outcome: str          # "ok" | "transient" | "timeout" | "rejected" | "crash"
    elapsed_ms: float
    sleep_ms: float = 0.0
    error: str | None = None


@dataclass
class CallResult:
    """One logical call: the final envelope plus everything it took to get there."""

    envelope: Envelope
    attempts: list[Attempt] = field(default_factory=list)
    total_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.envelope.get("ok"))

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    def trace(self) -> str:
        """One line per attempt, for the demo screenshots."""
        lines = []
        for a in self.attempts:
            tail = f" -> {a.error}" if a.error else ""
            sleep = f", slept {a.sleep_ms:.0f}ms" if a.sleep_ms else ""
            lines.append(
                f"    attempt {a.number}: {a.outcome} "
                f"({a.elapsed_ms:.1f}ms{sleep}){tail}"
            )
        return "\n".join(lines)


# --- the retry wrapper -----------------------------------------------------

def call_with_retry(
    fn: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy = INTERACTIVE_POLICY,
    rng: random.Random | None = None,
    **kwargs: Any,
) -> CallResult:
    """Call `fn` with a per-attempt timeout and bounded exponential backoff.

    Returns a CallResult whose `.envelope` is always a valid {ok, data, error}
    object. The three demonstrated behaviours fall out of this one function:

        no failures            -> 1 attempt, ok=True
        one transient failure  -> 2 attempts, ok=True
        failures throughout    -> max_attempts attempts, ok=False, no raise

    The timeout runs each attempt on a worker thread and abandons it if it
    overruns. The worker is not killed -- Python cannot safely do that -- so a
    hung call leaks one thread for as long as it keeps running. That is the
    accepted trade for a timeout in synchronous code, and it is bounded here
    because the tools are short database reads.
    """
    started = time.perf_counter()
    attempts: list[Attempt] = []
    last_error = "call failed"

    for attempt in range(1, policy.max_attempts + 1):
        attempt_started = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(fn, *args, **kwargs)
                result = future.result(timeout=policy.timeout_s)

        except FutureTimeout:
            elapsed = (time.perf_counter() - attempt_started) * 1000
            last_error = f"timed out after {policy.timeout_s:.2f}s"
            log.warning("attempt %d/%d timed out", attempt, policy.max_attempts)
            attempts.append(Attempt(attempt, "timeout", elapsed, error=last_error))

        except TransientError as exc:
            elapsed = (time.perf_counter() - attempt_started) * 1000
            last_error = str(exc) or "transient failure"
            log.warning("attempt %d/%d transient: %s", attempt, policy.max_attempts, last_error)
            attempts.append(Attempt(attempt, "transient", elapsed, error=last_error))

        except Exception as exc:  # noqa: BLE001
            # An unexpected exception is a bug, not a transient fault, so it is
            # not retried -- but it still must not escape, or the agent loop
            # dies on one bad tool.
            elapsed = (time.perf_counter() - attempt_started) * 1000
            last_error = f"{type(exc).__name__}: {exc}"
            log.exception("attempt %d raised an unexpected error", attempt)
            attempts.append(Attempt(attempt, "crash", elapsed, error=last_error))
            return CallResult(
                err(last_error), attempts, (time.perf_counter() - started) * 1000
            )

        else:
            elapsed = (time.perf_counter() - attempt_started) * 1000

            if not is_envelope(result):
                last_error = f"tool returned {type(result).__name__}, not an envelope"
                attempts.append(Attempt(attempt, "crash", elapsed, error=last_error))
                return CallResult(
                    err(last_error), attempts, (time.perf_counter() - started) * 1000
                )

            if result["ok"]:
                attempts.append(Attempt(attempt, "ok", elapsed))
                return CallResult(result, attempts, (time.perf_counter() - started) * 1000)

            # ok=False from the tool itself: the argument was rejected. The
            # same argument will be rejected again, so return it now.
            attempts.append(Attempt(attempt, "rejected", elapsed, error=result["error"]))
            return CallResult(result, attempts, (time.perf_counter() - started) * 1000)

        # Still here -> the attempt failed transiently. Back off, unless that
        # was the last allowed attempt.
        if attempt < policy.max_attempts:
            delay = policy.delay_for(attempt, rng)
            attempts[-1].sleep_ms = delay * 1000
            time.sleep(delay)

    total = (time.perf_counter() - started) * 1000
    log.error("giving up after %d attempts: %s", policy.max_attempts, last_error)
    return CallResult(
        err(f"failed after {policy.max_attempts} attempts: {last_error}"),
        attempts,
        total,
    )


# --- deterministic fault injection ----------------------------------------

class FaultInjector:
    """Wraps a callable and fails a fixed fraction of attempts, reproducibly.

    The spec: "Use VERIFY_SEED to reproducibly simulate failures at rates of
    0%, 20%, and 50%. The same seed must produce the same success/failure
    sequence each time."

    That is why the injector owns its own random.Random seeded from
    VERIFY_SEED, rather than touching the global `random` module: nothing else
    in the process can consume a draw and shift the sequence. Jitter uses a
    separate Random for the same reason -- if both drew from one stream, a
    retry's jitter would move every later fault decision.

    Draws happen per ATTEMPT, not per logical call, so a retried call consumes
    more than one. The sequence is still deterministic because the retry
    policy is.
    """

    def __init__(self, fn: Callable[..., Any], failure_rate: float, seed: int) -> None:
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0.0 and 1.0")
        self._fn = fn
        self.failure_rate = failure_rate
        self.seed = seed
        self._rng = random.Random(seed)
        self.draws = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.draws += 1
        if self._rng.random() < self.failure_rate:
            raise TransientError(
                f"injected failure (rate={self.failure_rate:.0%}, draw #{self.draws})"
            )
        return self._fn(*args, **kwargs)


class ScriptedFailures:
    """Fails exactly the attempts listed, then succeeds. For the three demos.

    ScriptedFailures(fn, fail_on=[1]) fails the first attempt and succeeds on
    the second -- which is demonstration #2 verbatim.
    """

    def __init__(self, fn: Callable[..., Any], fail_on: list[int]) -> None:
        self._fn = fn
        self._fail_on = set(fail_on)
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls in self._fail_on:
            raise TransientError(f"scripted failure on attempt {self.calls}")
        return self._fn(*args, **kwargs)


# --- latency statistics ----------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile.

    With n=50 per rate, p99 lands on the 50th sample -- i.e. the maximum. That
    is a real limitation of the sample size, not a bug, and the report says so
    rather than implying 50 calls can resolve a 99th percentile.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(-(-p * len(ordered) // 100))))
    return ordered[rank - 1]

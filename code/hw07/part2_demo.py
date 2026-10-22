#!/usr/bin/env python3
"""HW7 Part 2 - run tasks A, B, C and the nonexistent-ID case once each, temperature 0."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import run_agent  # noqa: E402
from tasks import MISSING, TASKS  # noqa: E402

from model_client import ModelClient  # noqa: E402


def main() -> int:
    model = ModelClient(temperature=0.0)
    print(f"# HW7 Part 2 demo - {time.strftime('%Y-%m-%d %H:%M:%S')} - Pragnaya Priyadarshini "
          f"SID4 3170 - model {model.model_name} temperature 0.0", flush=True)
    cases = [(k, *v) for k, v in TASKS.items()] + [("missing-ID", *MISSING)]
    failed = 0
    for label, prompt, check in cases:
        print(f"\n=== Task {label}: {prompt}", flush=True)
        run = run_agent(prompt, model=model)
        ok, why = check(run)
        failed += not ok
        print(f"  [check] {'PASS' if ok else 'FAIL'} - {why}", flush=True)
    return failed


if __name__ == "__main__":
    sys.exit(main())

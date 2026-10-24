#!/usr/bin/env python3
"""HW7 - assemble reports/hw07/RUN_LOG.txt from the real console logs the runs wrote.

Nothing is re-typed: each section is the captured output of the run that produced the reported
numbers, in the order the work was done, with Python/urllib3 warning noise filtered out and the
file's own timestamp header kept. Failed development attempts are included under their own
headings because they are part of how the final agent was reached."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "reports" / "hw07" / "raw"
OUT = REPO / "reports" / "hw07" / "RUN_LOG.txt"
NOISE = re.compile(r"warning|urllib3|NotOpenSSL|warnings\.warn", re.IGNORECASE)

SECTIONS = [
    ("Part 1 - lint demo: attempt 1, pre-commit blocks the commit", "lint_demo_1_fail.txt"),
    ("Part 1 - lint demo: attempt 2, issues fixed, commit succeeds", "lint_demo_2_fixed.txt"),
    ("Part 6 - glob/search/read integration test + safety-gate test", "part6_gate_test.txt"),
    ("Part 2 - tasks A, B, C and the nonexistent-ID case (temperature 0)", "part2_demo_run.txt"),
    ("Part 2 - 20-attempt reliability run (temperature 0.7)", "part2_reliability_run.txt"),
    ("Part 3 - original vs Reflexion, 12 paired runs", "part3_compare_run_raw.txt"),
    ("Part 4 - membership-wins scenario (final run)", "part4_run_membership_wins.txt"),
    ("Part 4 - pay-per-use-wins scenario (final run)", "part4_run_pay_per_use_wins.txt"),
    ("Part 5 - round 1, structured-prompt agent: 3 attacks x 3 defense levels", "part5_attacks_run_raw.txt"),
    ("Part 5 - round 2, naive-prompt baseline agent: 3 attacks x 3 defense levels", "part5_attacks_naive_run_raw.txt"),
    ("Part 5 - round 3, naive agent vs the stronger override/exfil fixtures", "part5_attacks_naive_strong_run_raw.txt"),
    ("Self-check - make verify-hw07 (live backend, live model)", "verify_hw07_run.txt"),
]
DEV = (["v1_initial/part2_demo_run.txt", "v1_initial/part2_reliability_run.txt", "v1_initial/part3_compare_run_raw.txt",
        "v2_lax_check/part2_demo_run.txt", "v2_lax_check/part2_reliability_run.txt", "v2_lax_check/part3_compare_run_raw.txt"]
       + [f"dev_history/{n}" for n in (
           "part2_demo_run_toolnotes_attempt1_taskC_regression.txt",
           "part2_demo_run_toolnotes_attempt2_taskC_still_fails.txt", "prompt_variant_trials.txt",
           "prompt_variant_trials_strict_check.txt")]
       + sorted(f"dev_history/{p.name}" for p in (RAW / "dev_history").glob("part4_run_*attempt*.txt"))
       + ["dev_history/part5_attacks_attempt1_stalled_on_cell3.txt"])


def clean(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not NOISE.search(ln)).strip()


def main() -> None:
    parts = ["HW7 RUN LOG - Pragnaya Priyadarshini, SID4 3170",
             "Real console output of the runs behind the reported results (logs filtered only for "
             "Python/urllib3 warning lines).", ""]
    for title, name in SECTIONS + [(f"Development history - {n}", n) for n in DEV]:
        path = RAW / name
        body = clean(path.read_text()) if path.exists() else "(log file not present)"
        parts += ["=" * 100, title, f"source: reports/hw07/raw/{name}", "=" * 100, body, ""]
    OUT.write_text("\n".join(parts))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

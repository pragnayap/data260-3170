#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 3.2 / 3.3 - is the judge trustworthy?

  python validate_judge.py            run the Writer-Helpfulness judge 3 times on the 20 frozen drafts, then report
  python validate_judge.py --stats    recompute the statistics from the saved raw runs (no model calls)

Refuses to run the judge unless
  * data/hw10/human_labels.csv has a hand-assigned 1-5 score for every case (no blanks), and
  * eval_cases.json and human_labels.csv are COMMITTED and unmodified (labels frozen before any judge score exists).

Outputs  reports/hw10/raw/judge_runs.json (raw per-case, per-run scores + reasons) and
         reports/hw10/raw/judge_validation.json (Spearman, mean absolute difference, repeatability, settings).
Run 1 is the Part 3.2 comparison; runs 1-3 together are the Part 3.3 repeatability test (same inputs, same settings).
"""
from __future__ import annotations

import csv
import json
import statistics as st
import subprocess
import sys
import time
from itertools import combinations

import common10 as c
from judge import CLIENT_TIMEOUT, JUDGE_MODEL, NUM_PREDICT, SEED, TEMPERATURE, JudgeError, LocalJudge, make_metrics, score
from scipy.stats import spearmanr

CASES, LABELS = c.DATA / "eval_cases.json", c.DATA / "human_labels.csv"
RUNS_OUT, STATS_OUT = c.RAW / "judge_runs.json", c.RAW / "judge_validation.json"
N_RUNS = 3


def load_inputs() -> tuple[list[dict], dict[str, int]]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    human: dict[str, int] = {}
    with LABELS.open(newline="") as fh:
        for row in csv.DictReader(fh):
            v = (row.get("human_score") or "").strip()
            if v:
                human[row["case_id"]] = int(v)
    return cases, human


def preflight(cases: list[dict], human: dict[str, int]) -> list[str]:
    problems = []
    if len(cases) != 20:
        problems.append(f"eval_cases.json has {len(cases)} cases, expected 20")
    missing = [x["case_id"] for x in cases if x["case_id"] not in human]
    if missing:
        problems.append(f"human_labels.csv has no score for: {', '.join(missing)}")
    bad = [k for k, v in human.items() if v not in (1, 2, 3, 4, 5)]
    if bad:
        problems.append(f"human scores must be integers 1-5; bad: {bad}")
    for f in (CASES, LABELS):
        rel = str(f.relative_to(c.ROOT))
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=c.ROOT, capture_output=True).returncode == 0
        dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=c.ROOT, capture_output=True, text=True).stdout.strip()
        if not tracked or dirty:
            problems.append(f"{rel} must be committed and unmodified before the judge runs (labels are frozen first)")
    return problems


def compute_stats(cases: list[dict], human: dict[str, int], runs: list[dict[str, int | None]]) -> dict:
    ids = [x["case_id"] for x in cases]
    out: dict = {"n_cases": len(ids), "n_runs": len(runs)}

    def vs_human(run: dict) -> dict:
        pairs = [(human[i], run[i]) for i in ids if run.get(i) is not None]
        h, j = [p[0] for p in pairs], [p[1] for p in pairs]
        rho = spearmanr(h, j).statistic if len(set(h)) > 1 and len(set(j)) > 1 else float("nan")
        return {"n_scored": len(pairs), "spearman": None if rho != rho else round(float(rho), 4),
                "mean_abs_diff": round(st.mean(abs(a - b) for a, b in pairs), 4) if pairs else None,
                "mean_signed_diff_judge_minus_human": round(st.mean(b - a for a, b in pairs), 4) if pairs else None}

    out["part_3_2_run1_vs_human"] = vs_human(runs[0])
    out["each_run_vs_human"] = [vs_human(r) for r in runs]
    rep_cases = [i for i in ids if all(r.get(i) is not None for r in runs)]
    ranges = [max(r[i] for r in runs) - min(r[i] for r in runs) for i in rep_cases]
    pair_diffs = [abs(a[i] - b[i]) for a, b in combinations(runs, 2) for i in rep_cases]
    out["repeatability"] = {
        "cases_compared": len(rep_cases),
        "cases_whose_score_changed_across_runs": sum(1 for x in ranges if x > 0),
        "fraction_cases_changed": round(sum(1 for x in ranges if x > 0) / len(rep_cases), 4) if rep_cases else None,
        "run_pair_comparisons": len(pair_diffs),
        "fraction_pair_comparisons_changed": round(sum(1 for x in pair_diffs if x > 0) / len(pair_diffs), 4) if pair_diffs else None,
        "mean_abs_change": round(st.mean(pair_diffs), 4) if pair_diffs else None,
        "max_abs_change": max(pair_diffs) if pair_diffs else None,
        "mean_range_per_case": round(st.mean(ranges), 4) if ranges else None,
        "max_range_per_case": max(ranges) if ranges else None}
    out["human_label_distribution"] = {str(k): sum(1 for v in human.values() if v == k) for k in range(1, 6)}
    return out


def main() -> int:
    c.banner("validate_judge.py")
    cases, human = load_inputs()
    if "--stats" in sys.argv:
        saved = json.loads(RUNS_OUT.read_text())
        runs = [{k: v["score"] for k, v in r["cases"].items()} for r in saved["runs"]]
        print(json.dumps(compute_stats(cases, human, runs), indent=2))
        return 0
    problems = preflight(cases, human)
    if problems:
        print("NOT RUNNING THE JUDGE:\n  - " + "\n  - ".join(problems))
        return 2
    judge = LocalJudge()
    metric = make_metrics(judge)["writer_helpfulness"]
    saved_runs, runs = [], []
    for r in range(1, N_RUNS + 1):
        scores: dict[str, dict] = {}
        t0 = time.time()
        for case in cases:
            try:
                s, reason = score(metric, case["question"], case["draft"])
                scores[case["case_id"]] = {"score": s, "reason": reason, "error": None}
            except JudgeError as exc:
                scores[case["case_id"]] = {"score": None, "reason": "", "error": str(exc)}
            print(f"run {r} {case['case_id']}  judge={scores[case['case_id']]['score']}  human={human[case['case_id']]}", flush=True)
        saved_runs.append({"run": r, "seconds": round(time.time() - t0, 1), "cases": scores})
        runs.append({k: v["score"] for k, v in scores.items()})
        RUNS_OUT.write_text(json.dumps({"settings": settings(), "runs": saved_runs}, indent=2))   # saved after every run
    stats = {"settings": settings(), **compute_stats(cases, human, runs)}
    STATS_OUT.write_text(json.dumps(stats, indent=2))
    print(json.dumps({k: v for k, v in stats.items() if k != "settings"}, indent=2))
    return 0


def settings() -> dict:
    return {"judge_model": JUDGE_MODEL, "framework": "DeepEval GEval (custom local model)", "temperature": TEMPERATURE,
            "seed": SEED, "thinking": "off", "num_predict": NUM_PREDICT, "client_timeout_s": CLIENT_TIMEOUT,
            "scale": "1-5 (rubric), same scale as the human labels", "metric": "Writer Helpfulness",
            "input": "question + Writer draft", "evaluation_steps": "fixed (judge.HELPFULNESS_STEPS)"}


if __name__ == "__main__":
    sys.exit(main())

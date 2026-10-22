#!/usr/bin/env python3
"""
HW7 Part 3.III - original loop vs Reflexion loop on the same fixed tasks.

Paired design: for every run, attempt 0 IS the original Part 2 loop and the final
outcome is the Reflexion loop, so both see the same task, model settings and first
sample. (temperature 0.7, 4 runs each of tasks A, B, C.)

Metrics
    success              verifier passed
    unsupported claims   answer states an incident code / 3+ digit number that no tool
                         result contains, or the verifier failed on the answer's content
    retry rate           retries per run
    tokens               model tokens (Reflexion includes the reflection-writing calls)
    verifier false reject  strict verifier FAILED but an independent looser oracle says
                         the answer is correct and grounded
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reflexion import RAW, run_reflexion  # noqa: E402
from tasks import TASKS, _tool  # noqa: E402

from model_client import ModelClient  # noqa: E402

PLAN = ["A"] * 4 + ["B"] * 4 + ["C"] * 4
TEMPERATURE = 0.7


def unsupported(run, why: str) -> bool:
    seen = " ".join(json.dumps(c["data"]) + str(c["error"]) for c in run.tool_log)
    ans = run.answer or ""
    claims = set(re.findall(r"INC-\d{4}-\d{5}", ans)) | set(re.findall(r"\b\d{3,}\b", ans))
    if any(c not in seen for c in claims):
        return True
    return why.startswith("answer does not") or why.startswith("no example")


def oracle(label: str, run) -> bool:
    """Looser, independent correctness test: is the key fact in the answer true?"""
    ans = (run.answer or "").lower()
    if label == "B":
        return _tool("incident_stats", group_by="category")["groups"][0]["group"].lower() in ans
    if label == "A":
        first = _tool("search_incidents", query="Main St", limit=1)["results"][0]
        return first["incident_code"].lower() in ans
    results = _tool("search_incidents", query="Main St & 4th Ave", limit=2)["results"]
    riders = {r["incident_code"]: _tool("incident_details", incident_code=r["incident_code"])
              ["riders_affected"] for r in results}
    win = max(riders, key=riders.get)
    win_route = next(r["route_id"] for r in results if r["incident_code"] == win).lower()
    # Looser than the verifier: the winner may be named by code, route, or rider count.
    return win.lower() in ans or win_route in ans or str(riders[win]) in ans


def main() -> None:
    model = ModelClient(temperature=TEMPERATURE)
    print(f"# HW7 Part 3 comparison - {time.strftime('%Y-%m-%d %H:%M:%S')} - Pragnaya "
          f"Priyadarshini SID4 3170 - {model.model_name} temperature {TEMPERATURE}", flush=True)
    results, reflections = [], []
    for i, label in enumerate(PLAN, 1):
        prompt, check = TASKS[label]
        print(f"\n=== run {i}/{len(PLAN)} task {label}", flush=True)
        before = model.cumulative.total_tokens
        res = run_reflexion(label, prompt, check, model=model)
        res["reflexion_tokens"] = model.cumulative.total_tokens - before
        first, last = res["attempts"][0], res["attempts"][-1]
        res["original"] = {
            "success": first["passed"], "tool_calls": first["tool_calls"],
            "tokens": first["tokens"], "elapsed_ms": first["elapsed_ms"],
            "unsupported": unsupported(first["run"], first["check"]),
            "false_reject": (not first["passed"]) and oracle(label, first["run"]),
        }
        res["reflexion"] = {
            "success": res["success"], "tool_calls": res["tool_calls"],
            "tokens": res["reflexion_tokens"], "elapsed_ms": res["elapsed_ms"],
            "unsupported": unsupported(last["run"], last["check"]),
            "false_reject": any((not a["passed"]) and oracle(label, a["run"])
                                for a in res["attempts"]),
        }
        reflections += res["reflections"]
        print(f"  [result] original={'PASS' if first['passed'] else 'FAIL'} "
              f"reflexion={'PASS' if res['success'] else 'FAIL'} stop={res['stop_reason']} "
              f"retries={res['retries']}", flush=True)
        results.append(res)

    slim = [{k: v for k, v in r.items() if k != "attempts"} |
            {"attempts": [{k: v for k, v in a.items() if k != "run"} for a in r["attempts"]]}
            for r in results]
    (RAW / "reflexion_comparison_runs.json").write_text(json.dumps(slim, indent=2))
    with (RAW / "reflections.jsonl").open("w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in reflections)

    n = len(results)

    def agg(side):
        rows = [r[side] for r in results]
        return {
            "task_success": f"{sum(x['success'] for x in rows)}/{n}",
            "unsupported_claims": sum(x["unsupported"] for x in rows),
            "retry_rate": "0.00" if side == "original" else
                          f"{sum(r['retries'] for r in results) / n:.2f}",
            "tool_calls": sum(x["tool_calls"] for x in rows),
            "tokens": sum(x["tokens"] for x in rows),
            "latency_ms": sum(x["elapsed_ms"] for x in rows),
            "verifier_false_rejections": sum(x["false_reject"] for x in rows),
        }

    summary = {"runs": n, "model": model.model_name, "temperature": TEMPERATURE,
               "original": agg("original"), "reflexion": agg("reflexion"),
               "stop_reasons": {s: sum(r["stop_reason"] == s for r in results)
                                for s in ("success", "budget_exhausted", "human_review")}}
    (RAW / "reflexion_comparison_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

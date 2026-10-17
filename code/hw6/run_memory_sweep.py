"""
HW6 Part 3 - run the 30-message conversation + 5 probes against the live API
under each memory setting, and write per-turn rows and probe scores to raw/.

Backend must be running (`make run`) with MongoDB and Ollama up.

    python -u code/hw6/run_memory_sweep.py            # all four settings
    python -u code/hw6/run_memory_sweep.py N12        # just one label

Each setting gets a fresh user_id (and so a fresh session, summaries and
episodes), so nothing carries over between runs. A setting whose
probe_scores_<label>.json already exists is skipped, so an interrupted sweep
resumes where it stopped (delete the file to force a re-run).
"""

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conversation import CONVERSATION  # noqa: E402
from probes import load_probes, score_reply  # noqa: E402

API = "http://localhost:8470"
RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"

SETTINGS = {
    "N4": {"short_term_n": 4, "policy": "none"},
    "N12": {"short_term_n": 12, "policy": "none"},
    "N30": {"short_term_n": 30, "policy": "none"},
    "N30_evict": {"short_term_n": 30, "policy": "evict_old_assistant"},
}

FIELDS = [
    "label", "turn", "phase", "prompt_tokens", "completion_tokens",
    "tok_system_primer", "tok_long_term_summary", "tok_short_term_window", "tok_episodic_facts", "tok_current_message",
    "latency_ms", "total_latency_ms", "extraction_in", "extraction_out", "summary_in", "summary_out",
    "short_term_count", "episodic_retrieved",
]


def stamp(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_setting(label: str, cfg: dict, client: httpx.Client) -> None:
    probes = load_probes()
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    user_id, session_id = f"hw6_{label}_{run_id}", f"sess_{label}_{run_id}"
    rows, probe_results = [], []
    stamp(f"=== {label} {cfg} user_id={user_id}")

    def turn(i: int, phase: str, text: str) -> dict:
        body = {"user_id": user_id, "session_id": session_id, "message": text, "run_label": label, **cfg}
        r = client.post(f"{API}/api/chat", json=body)
        r.raise_for_status()
        d = r.json()
        m, c = d["metrics"], d["metrics"]["component_tokens"]
        rows.append({
            "label": label, "turn": i, "phase": phase,
            "prompt_tokens": m["prompt_tokens"], "completion_tokens": m["completion_tokens"],
            "tok_system_primer": c["system_primer"], "tok_long_term_summary": c["long_term_summary"],
            "tok_short_term_window": c["short_term_window"], "tok_episodic_facts": c["episodic_facts"],
            "tok_current_message": c["current_message"],
            "latency_ms": m["latency_ms"], "total_latency_ms": m["total_latency_ms"],
            "extraction_in": m["overhead_tokens"]["extraction_in"], "extraction_out": m["overhead_tokens"]["extraction_out"],
            "summary_in": m["overhead_tokens"]["summary_in"], "summary_out": m["overhead_tokens"]["summary_out"],
            "short_term_count": d["memory_used"]["short_term_count"],
            "episodic_retrieved": len(d["memory_used"]["episodic_facts"]),
        })
        stamp(f"{label} turn {i:>2} [{phase}] prompt={m['prompt_tokens']} completion={m['completion_tokens']} "
              f"latency={m['latency_ms']}ms window={rows[-1]['short_term_count']} episodes={rows[-1]['episodic_retrieved']}")
        return d

    for i, text in enumerate(CONVERSATION, start=1):
        turn(i, "conversation", text)
    for j, probe in enumerate(probes["probes"], start=31):
        d = turn(j, "probe", probe["question"])
        res = score_reply(d["reply"], probe, probes["refusal"])
        res["question"], res["reply"] = probe["question"], d["reply"]
        probe_results.append(res)
        stamp(f"{label} probe {probe['id']} score={res['score']} matched={res['matched']}")

    with (RAW / f"turns_{label}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (RAW / f"probe_scores_{label}.json").write_text(json.dumps(
        {"label": label, "settings": cfg, "user_id": user_id, "session_id": session_id,
         "mean_score": round(sum(p["score"] for p in probe_results) / len(probe_results), 3),
         "probes": probe_results}, indent=2))
    stamp(f"=== {label} done: mean probe score "
          f"{sum(p['score'] for p in probe_results) / len(probe_results):.2f}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(SETTINGS)
    with httpx.Client(timeout=900) as client:
        for label in wanted:
            if (RAW / f"probe_scores_{label}.json").exists():
                stamp(f"skip {label}: probe_scores_{label}.json exists")
                continue
            run_setting(label, SETTINGS[label], client)


if __name__ == "__main__":
    main()

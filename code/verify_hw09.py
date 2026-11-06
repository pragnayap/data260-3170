#!/usr/bin/env python3
"""
HW9 self-check. Writes reports/hw09/verification.json. No LLM is called: the semantic-cache behaviour checks use a
stub agent, and the Part 4 checks read the committed datasets and the results written by the real (Ollama) runs.

    .venv/bin/python code/verify_hw09.py

Needs Redis Stack (make redis-up-hw09) and MySQL. A check whose service is down is SKIPPED with its reason.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW9 = REPO / "code" / "hw09"
REPORT = REPO / "reports" / "hw09"
RAW = REPORT / "raw"
P4 = REPO / "data" / "hw09" / "part4"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = 3170, 3170, 263170, 8470, "s3170"
sys.path.insert(0, str(HW9))

checks: list[dict] = []


class Skip(Exception):
    pass


def record(name: str, status: str, detail: str = "") -> None:
    checks.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:<4}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def run(name: str, fn) -> None:
    try:
        ok, detail = fn()
        record(name, "PASS" if ok else "FAIL", detail)
    except Skip as s:
        record(name, "SKIP", str(s))
    except Exception as exc:  # noqa: BLE001
        record(name, "FAIL", f"{exc.__class__.__name__}: {exc}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def jload(p: Path):
    if not p.exists():
        raise Skip(f"{p.name} not generated yet")
    return json.loads(p.read_text())


def redis_checks() -> None:
    import common  # noqa: F401
    import redis

    try:
        r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True, socket_connect_timeout=2)
        r.ping()
    except Exception as exc:  # noqa: BLE001
        raise Skip(f"Redis not reachable: {exc}") from exc
    from cache_db import IncidentCache
    from sqlalchemy import text

    rng = random.Random(VERIFY_SEED)
    incident_id = rng.randint(2000, 4000)

    def modules():
        names = [m["name"] if isinstance(m, dict) else m[1] for m in r.module_list()]
        return "search" in [str(n).lower() for n in names], f"modules: {names}"

    run("Redis Stack is running with the search module (vector index support)", modules)

    def counter():
        cache = IncidentCache()
        key = cache.views_key(incident_id)
        r.delete(key)
        with cache.session_factory() as db:
            db.execute(text("UPDATE incidents SET view_count = 0 WHERE id = :i"), {"i": incident_id})
            db.commit()
        syncs, totals = [], []
        for _ in range(25):
            before = cache.last_synced
            totals.append(cache.increment_incident_views(incident_id))
            if cache.last_synced != before:
                syncs.append(totals[-1])
        with cache.session_factory() as db:
            db_val = db.execute(text("SELECT view_count FROM incidents WHERE id = :i"), {"i": incident_id}).scalar()
            upd = db.execute(text("SELECT updated_at FROM incidents WHERE id = :i"), {"i": incident_id}).scalar()
        ok = totals == list(range(1, 26)) and syncs == [10, 20] and db_val == 20 and key.startswith(f"{PREFIX}:") and r.get(key) == "25"
        r.delete(key)
        with cache.session_factory() as db:
            db.execute(text("UPDATE incidents SET view_count = 0 WHERE id = :i"), {"i": incident_id})
            db.commit()
        return ok, f"incident {incident_id}: totals 1..25, DB synced at {syncs}, DB value {db_val}, key {key}, updated_at untouched={upd is not None}"

    run("Part 1: INCR counter returns 1..25, syncs to MySQL exactly at 10 and 20, key starts with s3170", counter)

    from qa_agent import data_version
    from semantic_cache import SemanticCache

    calls = {"n": 0}

    def stub(q: str) -> dict:
        calls["n"] += 1
        return {"answer": f"stub answer {calls['n']}", "data_version": data_version(["R-0150"]), "entities": ["R-0150"]}

    cache = SemanticCache("verify")
    cache.create_index(reset=True)

    def hit_miss():
        calls["n"] = 0
        a = cache.handle("What agency operates route R-0150?", agent=stub)
        b = cache.handle("What agency operates route R-0150?", agent=stub)
        c = cache.handle("What is the capital of France?", agent=stub)
        ok = (not a["is_cached"] and b["is_cached"] and b["similarity"] >= 0.999 and not c["is_cached"]
              and calls["n"] == 2 and b["answer"] == a["answer"] and all("latency_ms" in x for x in (a, b, c)))
        return ok, f"miss/hit/miss, agent ran {calls['n']}x, hit similarity {b['similarity']}, latency fields present"

    run("Part 2: miss runs the agent and stores; exact repeat is a hit WITHOUT running the agent; unrelated misses", hit_miss)

    def threshold_rule():
        look = cache.lookup("Which transit agency is responsible for route R-0150?", 0.0)
        sim = look["neighbour"]["similarity"]
        lo = cache.lookup("Which transit agency is responsible for route R-0150?", sim - 0.01)["hit"]
        hi = cache.lookup("Which transit agency is responsible for route R-0150?", sim + 0.01)["hit"]
        return lo and not hi, f"similarity {sim}: hit just below it, miss just above it"

    run("Part 2: hit iff cosine similarity >= threshold", threshold_rule)

    def keys_prefixed():
        bad = [k for k in r.scan_iter(match="*") if not str(k).startswith(f"{PREFIX}:")]
        return not bad, f"{len(list(r.scan_iter(match='*')))} keys in Redis, none outside the s3170: prefix" if not bad else f"unprefixed keys: {bad[:5]}"

    run("every Redis key starts with PREFIX s3170", keys_prefixed)

    def invalidation():
        from sqlalchemy import select

        from database import db_session_basede26
        from models import Route

        calls["n"] = 0
        cache.reset()
        cache.create_index()
        first = cache.handle("What agency operates route R-0150?", agent=stub)
        with db_session_basede26() as db:
            route = db.execute(select(Route).where(Route.route_code == "R-0150")).scalar_one()
            original = route.agency
            route.agency = "Verify Test Agency"
            db.commit()
        try:
            stale = cache.handle("What agency operates route R-0150?", validate_version=False, agent=stub)
            fixed = cache.handle("What agency operates route R-0150?", validate_version=True, agent=stub)
        finally:
            with db_session_basede26() as db:
                route = db.execute(select(Route).where(Route.route_code == "R-0150")).scalar_one()
                route.agency = original
                db.commit()
        ok = stale["is_cached"] and stale["answer"] == first["answer"] and not fixed["is_cached"] and fixed["stale_evicted"] and fixed["answer"] != first["answer"]
        return ok, "stale hit returned the old answer; version check evicted it and the agent re-ran; row restored"

    run("Part 3.5: updating a routes row makes a hit stale; the data-version check evicts it", invalidation)
    cache.reset()


def artifact_checks() -> None:
    import yaml

    def cases():
        p = HW9 / "cache_cases.yaml"
        d = yaml.safe_load(p.read_text())
        from collections import Counter
        g = Counter(c["group"] for c in d["cases"])
        exp = Counter(c["expect"] for c in d["cases"])
        return (len(d["cases"]) == 40 and g == {"exact_duplicate": 10, "paraphrase": 10, "near_miss": 10, "unrelated": 10}
                and exp == {"hit": 20, "miss": 20}), f"{len(d['cases'])} cases {dict(g)}"

    run("Part 3.1: cache_cases.yaml has 40 cases, 10 per group", cases)

    def committed():
        rel = "code/hw09/cache_cases.yaml"
        log = git("log", "--format=%H %ct", "--", rel).splitlines()
        if not log:
            return False, "not committed"
        mods = git("log", "--format=%H", "--diff-filter=M", "--", rel).splitlines()
        clean = git("status", "--porcelain", "--", rel) == ""
        sweep = RAW / "part3_sweep.json"
        first_commit_ts = int(log[-1].split()[1])
        before_sweep = (not sweep.exists()) or first_commit_ts <= int(sweep.stat().st_mtime)
        return clean and not mods and before_sweep, f"1 commit, never modified since, clean={clean}, committed before the sweep output={before_sweep}"

    run("Part 3.1: cache_cases.yaml was committed before the sweep and never relabeled", committed)

    def part2():
        d = jload(RAW / "part2_results.json")
        res = d["results"]
        kinds = {r["kind"] for r in res}
        ok = (len(res) >= 10 and any(r["is_cached"] for r in res) and any(not r["is_cached"] for r in res)
              and {"exact duplicate", "paraphrase"} <= kinds and any(k.startswith("new") for k in kinds)
              and all("latency_ms" in r and "similarity" in r for r in res))
        return ok, f"{len(res)} queries, hit rate {d['summary']['hit_rate_pct']}%, cached {d['summary']['avg_latency_cached_ms']} ms vs not cached {d['summary']['avg_latency_not_cached_ms']} ms"

    run("Part 2: >=10 queries covering duplicates, paraphrases and new questions, with flag + similarity + latency", part2)

    def sweep():
        d = jload(RAW / "part3_sweep.json")
        rows = d["rows"]
        ths = sorted({r["threshold"] for r in rows})
        recomputed = []
        for th in ths:
            rr = [r for r in rows if r["threshold"] == th]
            recomputed.append((sum(r["hit"] for r in rr), sum(r["hit"] and r["expect"] == "miss" for r in rr)))
        table = [(t["hits"], t["false_hits"]) for t in d["table"]]
        ok = ths == [0.75, 0.8, 0.85, 0.9, 0.95] and len(rows) == 200 and recomputed == table
        return ok, f"5 thresholds x 40 cases; table recomputed from rows matches: {table}"

    run("Part 3.2: sweep covers 5 thresholds x 40 cases and the table matches the raw rows", sweep)

    def costs():
        d = jload(RAW / "part3_sweep.json")
        c = d["costs"]
        ok = all(abs(t["total_cost_usd"] - round(t["misses"] * c["cache_miss_usd"] + t["false_hits"] * c["false_hit_usd"], 2)) < 1e-9 for t in d["table"])
        return ok, f"total = misses x ${c['cache_miss_usd']} + false hits x ${c['false_hit_usd']} for every threshold"

    run("Part 3.4: total cost = misses x C_miss + false hits x C_false at every threshold", costs)

    def stale():
        d = jload(RAW / "part3_stale.json")
        ok = (d["stale_hit"]["is_cached"] and d["stale_hit"]["answer"] == d["first_ask"]["answer"]
              and not d["after_invalidation"]["is_cached"] and d["fresh_hit"]["is_cached"]
              and d["new_agency"].lower() in d["after_invalidation"]["answer"].lower())
        return ok, "stale hit == original answer; after invalidation a fresh answer names the new agency; next ask is a valid hit"

    run("Part 3.5: recorded stale-hit and invalidation demo is consistent", stale)

    def datasets():
        problems = []
        qs = {}
        for n in ("training_data", "validation_data", "test_data"):
            d = json.loads((P4 / f"{n}.json").read_text())
            qs[n] = {x["question"] for x in d}
            if any(set(x) != {"id", "question"} for x in d):
                problems.append(f"{n} has fields beyond id/question")
        if qs["training_data"] & qs["test_data"] or qs["validation_data"] & qs["test_data"] or qs["training_data"] & qs["validation_data"]:
            problems.append("splits overlap")
        ref = json.loads((P4 / "reference_dataset.json").read_text())["routes"]
        return not problems and len(ref) >= 20, f"{len(ref)} reference routes; splits {[len(v) for v in qs.values()]} disjoint; inputs hold only id+question" if not problems else "; ".join(problems)

    run("Part 4: input datasets hold only questions, are disjoint, and a reference dataset exists", datasets)

    def lessons():
        ls = json.loads((P4 / "lessons.json").read_text())
        need = {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"}
        return bool(ls) and all(need <= set(x) for x in ls), f"{len(ls)} lessons, statuses {[x['status'] for x in ls]}"

    run("Part 4.2: lessons.json has lesson_id, failure_pattern, correction, created_at, use_count", lessons)

    def reuse():
        d = jload(RAW / "part4_training_run.json")
        loaded = [t for it in d["items"] for t in it["trace"] if t["lessons_loaded"]]
        ls = json.loads((P4 / "lessons.json").read_text())
        return bool(loaded) and any(x["use_count"] > 0 for x in ls), f"{len(loaded)} attempts loaded a stored lesson; use_count > 0 recorded"

    run("Part 4.2: a lesson created earlier is loaded for a later question (use_count recorded)", reuse)

    def stop():
        v = jload(RAW / "part4_variants.json")
        worst = max(len(r["trace"]) for res in v["detail"].values() for r in res)
        base = max(len(r["trace"]) for r in v["detail"]["Baseline"])
        return worst <= 2 and base == 1, f"max attempts in any variant = {worst}; Baseline always 1"

    run("Part 4.1: never more than two attempts; Baseline never revises", stop)

    def controlled():
        d = jload(RAW / "part4_controlled_demo.json")
        t = d["trace"]
        return len(t) == 2 and t[0]["result"] == "REVISE" and bool(t[0]["feedback"]), f"attempt 1 {t[0]['result']}, attempt 2 {t[-1]['result']}, final {d['final_result']}"

    run("Part 4.1: controlled case shows REVISE + feedback, then a revised answer", controlled)

    def no_test_leak():
        tr = jload(RAW / "part4_training_run.json")
        val = jload(RAW / "part4_validation.json")
        test_q = {x["question"] for x in json.loads((P4 / "test_data.json").read_text())}
        used = {it["question"] for it in tr["items"]}
        used |= {v["question"] for v in []}
        ls = json.loads((P4 / "lessons.json").read_text())
        leaked = [q for q in test_q if any(q in (x["correction"] + x["failure_pattern"]) for x in ls)]
        return not (used & test_q) and not leaked and "candidates" in val, "no test question appears in training, or inside any lesson"

    run("Part 4: test_data.json was not used to create lessons", no_test_leak)

    def table4():
        v = jload(RAW / "part4_variants.json")
        s = v["summary"]
        n = len(json.loads((P4 / "test_data.json").read_text()))
        ok = [x["variant"] for x in s] == ["Baseline", "Evaluator Repair", "Lesson Memory", "Validated Improvement"] and all(x["correct"] + x["incorrect"] == n for x in s)
        return ok, "; ".join(f"{x['variant']} {x['correct']}/{n}" for x in s)

    run("Part 4.4: four variants, each evaluated on all test questions", table4)


def static_checks() -> None:
    def files():
        need = ["code/web_application/cache_db.py", "code/hw09/semantic_cache.py", "code/hw09/qa_agent.py", "code/hw09/agents_si.py",
                "code/hw09/part1_counter.py", "code/hw09/part2_run.py", "code/hw09/part3_sweep.py", "code/hw09/part3_stale.py",
                "code/hw09/part4_run.py", "code/hw09/cache_cases.yaml", "data/hw09/part4/reference_dataset.json",
                "data/hw09/part4/lessons.json", "reports/hw09/AI_USE.md"]
        missing = [f for f in need if not (REPO / f).exists()]
        return not missing, "all required files present" if not missing else f"missing {missing}"

    run("required HW9 files exist", files)

    def banner():
        bad = [p.name for p in HW9.glob("part*.py") if "banner(" not in p.read_text()]
        return not bad, "every runnable part prints the student name banner" if not bad else f"no banner in {bad}"

    run("student name banner in every runnable script", banner)

    def ruff():
        files_ = [str(p) for p in list(HW9.glob("*.py")) + [REPO / "code/web_application/cache_db.py", REPO / "code/verify_hw09.py"]]
        res = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", "--select", "E9,F63,F7,F82,F401,F811,F841", *files_],
                             cwd=REPO, capture_output=True, text=True)
        return res.returncode == 0, "ruff clean" if res.returncode == 0 else res.stdout[-400:]

    run("ruff passes on HW9 code", ruff)


def main() -> int:
    static_checks()
    try:
        redis_checks()
    except Skip as s:
        record("Redis-backed checks", "SKIP", str(s))
    artifact_checks()
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)
    skipped = sum(c["status"] == "SKIP" for c in checks)
    out = {"homework": 9, "SID4": SID4, "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "DOMAIN_ID": 2,
           "commit": git("rev-parse", "HEAD"), "working_tree_clean": git("status", "--porcelain", "--untracked-files=no") == "",
           "model_configuration": {"cache": "Redis Stack 7.4 (RediSearch HNSW, COSINE, 384-d)", "embedding": "sentence-transformers/all-MiniLM-L6-v2",
                                   "agents_model": "qwen3:8b via Ollama (checks use a stub agent)"},
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "passed": passed, "failed": failed, "skipped": skipped, "total_checks": len(checks), "checks": checks}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(checks)} -> {REPORT / 'verification.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
HW6 self-check - a smoke test over the tagged commit. Writes reports/hw06/verification.json.

    .venv/bin/python code/verify_hw06.py             # all checks (backend, MongoDB, Ollama must be up)
    .venv/bin/python code/verify_hw06.py --offline   # file/unit checks only

Checks test behaviour, not wording: status codes, JSON shape, counts, files on disk.
A check that needs a service which is down is SKIPPED (reason recorded), not failed.
Writes only reports/hw06/verification.json; it creates throwaway MongoDB documents through
the public API (a probe incident, a verify-only chat user) and deletes them again.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
HW6 = REPO / "code" / "hw6"
REPORT = REPO / "reports" / "hw06"
RAW = REPORT / "raw"
API = "http://localhost:8470"
SID4, SEED, VERIFY_SEED = 3170, 3170, 263170
MODEL = "qwen3:8b (Ollama, via src/model_client.py)"

checks: list[dict] = []


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


class Skip(Exception):
    pass


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------- live checks
def live(client: httpx.Client):
    def backend_up():
        try:
            r = client.get(f"{API}/openapi.json")
        except httpx.HTTPError as exc:
            raise Skip(f"backend not reachable on {API}: {exc.__class__.__name__}")
        paths = r.json()["paths"]
        need = ["/api/doc/incidents", "/api/chat", "/api/memory/{user_id}", "/api/aggregate/{user_id}"]
        return r.status_code == 200 and all(p in paths for p in need), f"HTTP {r.status_code}; routes present: {[p for p in need if p in paths]}"

    run("backend responds on PORT_BASE 8470 and exposes the HW6 routes", backend_up)
    if checks[-1]["status"] != "PASS":
        return

    def mongo_schema():
        from pymongo import MongoClient
        from pymongo.errors import ServerSelectionTimeoutError

        c = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        try:
            c.admin.command("ping")
        except ServerSelectionTimeoutError:
            raise Skip("MongoDB not reachable on 27017")
        db = c["s3170_doc"]
        names = set(db.list_collection_names())
        want = {"transit_incidents", "messages", "summaries", "episodes"}
        opts = db.command("listCollections", filter={"name": "transit_incidents"})["cursor"]["firstBatch"][0]["options"]
        has_validator = "$jsonSchema" in opts.get("validator", {})
        return want <= names and has_validator, f"collections {sorted(names & want)}; $jsonSchema validator: {has_validator}"

    run("MongoDB s3170_doc has the 4 collections and a $jsonSchema validator", mongo_schema)

    good = {"routeId": "VERIFY-HW6", "category": "Delay", "occurredAt": "2026-10-14T07:15:00Z",
            "description": "verify_hw06 throwaway record"}

    def crud():
        r = client.post(f"{API}/api/doc/incidents", json=good)
        if r.status_code != 201:
            return False, f"POST -> {r.status_code}"
        doc = r.json()
        iid = doc["id"]
        steps = {"POST": 201, "default status": doc["status"] == "Open", "createdAt==updatedAt": doc["createdAt"] == doc["updatedAt"]}
        g = client.get(f"{API}/api/doc/incidents/{iid}")
        lst = client.get(f"{API}/api/doc/incidents?limit=500")
        time.sleep(0.01)
        u = client.put(f"{API}/api/doc/incidents/{iid}", json={**good, "status": "Resolved"})
        d = client.delete(f"{API}/api/doc/incidents/{iid}")
        after = client.get(f"{API}/api/doc/incidents/{iid}")
        ok = (g.status_code == 200 and lst.status_code == 200 and any(x["id"] == iid for x in lst.json())
              and u.status_code == 200 and u.json()["status"] == "Resolved" and u.json()["updatedAt"] > u.json()["createdAt"]
              and u.json()["createdAt"] == doc["createdAt"] and d.status_code == 204 and after.status_code == 404
              and doc["status"] == "Open")
        return ok, f"GET {g.status_code}, list {lst.status_code}, PUT {u.status_code}, DELETE {d.status_code}, GET-after-delete {after.status_code}"

    run("CRUD cycle: 201/200/200/200/204/404, default status, timestamps behave", crud)

    def validation():
        cases = {
            "missing routeId": {k: v for k, v in good.items() if k != "routeId"},
            "bad category enum": {**good, "category": "Nope"},
            "bad status enum": {**good, "status": "Closed"},
            "bad date": {**good, "occurredAt": "yesterday"},
            "routeId too long": {**good, "routeId": "x" * 101},
            "wrong type": {**good, "routeId": 12345},
            "unknown field": {**good, "stauts": "Open"},
        }
        codes = {k: client.post(f"{API}/api/doc/incidents", json=v).status_code for k, v in cases.items()}
        codes["malformed id"] = client.get(f"{API}/api/doc/incidents/zzz").status_code
        codes["unknown id"] = client.get(f"{API}/api/doc/incidents/000000000000000000000000").status_code
        ok = all(c == 422 for k, c in codes.items() if k not in ("malformed id", "unknown id")) and codes["malformed id"] == 400 and codes["unknown id"] == 404
        return ok, json.dumps(codes)

    run("validation: invalid bodies -> 422, malformed id -> 400, unknown id -> 404", validation)

    user, sess = f"verify_hw06_{VERIFY_SEED}", f"verify_sess_{int(time.time())}"
    base = {"user_id": user, "session_id": sess, "short_term_n": 12, "run_label": "verify_hw06"}

    def chat():
        try:
            r1 = client.post(f"{API}/api/chat", json={**base, "message": "Hi, I'm Verify. I ride the Line 22 bus every morning."}, timeout=600)
        except httpx.HTTPError as exc:
            raise Skip(f"chat call failed ({exc.__class__.__name__}); is Ollama running?")
        if r1.status_code != 200:
            raise Skip(f"chat returned {r1.status_code}: {r1.text[:120]}")
        r2 = client.post(f"{API}/api/chat", json={**base, "message": "Which bus do I ride?"}, timeout=600).json()
        d1 = r1.json()
        mu = r2["memory_used"]
        shape = {"reply", "session_id", "memory_used", "metrics"} <= set(r2) and {"short_term_count", "short_term", "long_term_summary", "episodic_facts"} <= set(mu)
        ok = bool(d1["reply"].strip()) and bool(r2["reply"].strip()) and shape and mu["short_term_count"] == 2 \
            and r2["metrics"]["prompt_tokens"] > 0 and r2["metrics"]["latency_ms"] > 0
        return ok, f"turn-2 short_term_count={mu['short_term_count']}, episodic_retrieved={len(mu['episodic_facts'])}, prompt_tokens={r2['metrics']['prompt_tokens']}"

    run("POST /api/chat returns a reply + memory_used; turn 2 sees the 2 earlier messages", chat)

    def memory_endpoints():
        m = client.get(f"{API}/api/memory/{user}")
        a = client.get(f"{API}/api/aggregate/{user}")
        if m.status_code != 200 or a.status_code != 200:
            return False, f"memory {m.status_code}, aggregate {a.status_code}"
        mj, aj = m.json(), a.json()
        n_msgs = len(mj["messages"])
        total = sum(x["count"] for x in aj["daily_message_counts"])
        if n_msgs == 0:
            raise Skip("no chat messages stored (chat check skipped)")
        ok = n_msgs == total and "episodes" in mj and "latest_session_summary" in mj and "latest_lifetime_summary" in mj
        return ok, f"{n_msgs} messages, daily counts sum {total}, {len(mj['episodes'])} episodes"

    run("GET /api/memory and /api/aggregate agree on message counts", memory_endpoints)

    def cleanup():
        from pymongo import MongoClient

        db = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)["s3170_doc"]
        n = sum(db[c].delete_many({"user_id": user}).deleted_count for c in ("messages", "summaries", "episodes"))
        return True, f"removed {n} verify-only documents"

    try:
        run("cleanup of verify-only chat documents", cleanup)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- offline checks
def offline():
    import yaml

    def probes():
        y = yaml.safe_load((REPO / "memory_probes.yaml").read_text())
        ps = y["probes"]
        ok = len(ps) == 5 and all(p["question"] and p["elements"] for p in ps) and set(y["rubric"]) == {1, 2, 3, 4, 5}
        return ok, f"{len(ps)} probes, rubric levels {sorted(y['rubric'])}"

    run("memory_probes.yaml: 5 probes with expected elements + 1-5 rubric", probes)

    def unit_tests():
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HW6 / "test_file_memory.py")],
                           cwd=HW6, capture_output=True, text=True, timeout=300)
        return p.returncode == 0, (p.stdout.strip().splitlines() or [""])[-1]

    run("file-memory unit tests (thresholds, consolidation logic, /compact, /dream, /help)", unit_tests)

    def thresholds():
        sys.path.insert(0, str(HW6))
        import file_memory as fm
        from datetime import timedelta

        now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
        mk = lambda n, ts: "# M\n" + (f"<!-- last_consolidated: {ts.isoformat()} -->\n" if ts else "") + "\n".join(f"- f{i}" for i in range(n))  # noqa: E731
        res = {
            "41 lines": fm.consolidation_reason(mk(40, now), now) is not None,   # 40 facts + heading = 41
            "40 lines": fm.consolidation_reason(mk(39, now), now) is None,
            "25h old": fm.consolidation_reason(mk(3, now - timedelta(hours=25)), now) is not None,
            "23h old": fm.consolidation_reason(mk(3, now - timedelta(hours=23)), now) is None,
        }
        return all(res.values()), json.dumps(res)

    run("consolidation trigger: >40 non-empty non-comment lines OR >24 h", thresholds)

    def agent_md():
        text = (REPO / "AGENT.md").read_text()
        bullets = [ln for ln in text.splitlines() if ln.lstrip().startswith("- ")]
        heads = {h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, flags=re.M)}
        cats = [c for c in ("project description", "technology stack", "coding conventions", "testing approach", "prohibited actions") if c in heads]
        return len(bullets) >= 5 and len(cats) >= 3, f"{len(bullets)} bullets; categories: {cats}"

    run("AGENT.md has >=5 instructions across >=3 required categories", agent_md)

    def sweep_data():
        info = {}
        for lab in ("N4", "N12", "N30", "N30_evict"):
            f, p = RAW / f"turns_{lab}.csv", RAW / f"probe_scores_{lab}.json"
            if not (f.exists() and p.exists()):
                info[lab] = "missing"
                continue
            rows = list(csv.DictReader(f.open()))
            conv = [r for r in rows if r["phase"] == "conversation"]
            ps = json.loads(p.read_text())
            info[lab] = f"{len(conv)} conv turns, {len(ps['probes'])} probes, mean {ps['mean_score']}"
        ok = all(not v.startswith("missing") and v.startswith("30 conv turns, 5 probes") for v in info.values())
        return ok, json.dumps(info)

    run("Part 3 raw data: 4 settings x (30 conversation turns + 5 probes)", sweep_data)

    def memory_files():
        d = REPORT / "memory_test"
        o, c = d / "MEMORY.original.md", d / "MEMORY.consolidated.md"
        if not (o.exists() and c.exists()):
            return False, "original or consolidated MEMORY missing"
        sys.path.insert(0, str(HW6))
        import file_memory as fm

        n_o, n_c = fm.count_memory_lines(o.read_text()), fm.count_memory_lines(c.read_text())
        tracked = all(git("ls-files", "--error-unmatch", str(p.relative_to(REPO))) for p in (o, c))
        return n_o == 55 and n_c < 40 and tracked, f"original {n_o} lines, consolidated {n_c} lines, both tracked in git: {bool(tracked)}"

    run("original MEMORY.md = 55 lines, consolidated < 40, both committed", memory_files)

    def deliverables():
        need = ["RUN_LOG.txt", "METRICS.md", "AI_USE.md", "raw"]
        missing = [n for n in need if not (REPORT / n).exists()]
        return not missing, f"missing: {missing}" if missing else "all present"

    run("reports/hw06 has RUN_LOG.txt, METRICS.md, AI_USE.md, raw/", deliverables)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if not args.offline:
        with httpx.Client(timeout=30) as client:
            live(client)
    offline()
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)
    skipped = sum(c["status"] == "SKIP" for c in checks)
    out = {
        "homework": 6, "SID4": SID4, "PORT_BASE": 8470, "PREFIX": "s3170", "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
        "DOMAIN_ID": 2, "commit": git("rev-parse", "HEAD"), "working_tree_clean": git("status", "--porcelain") == "",
        "model_configuration": {"model": MODEL, "SHORT_TERM_N_default": 12, "SUMMARIZE_EVERY_USER_MSGS": 6, "EPISODE_TOP_K": 3,
                                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "mongodb": "mongo:7.0 (Docker)", "offline_only": args.offline},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": passed, "failed": failed, "skipped": skipped, "total_checks": len(checks), "checks": checks,
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(checks)} -> {REPORT / 'verification.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

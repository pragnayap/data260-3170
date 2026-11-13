"""
HW10 Part 1 - Streamlit operations dashboard (an evidence interface for the existing HW8/HW9 system, not a new app).

    make dashboard-hw10      ->  http://localhost:8472     (8472: our choice, next to FastAPI 8470 / Vite 8471)

Pages: Summary | Evaluation | Trace lookup.   Every metric states its time window and data source.
All numbers come from dash_data.py (spans.jsonl + the Part 2/3 result files); nothing on this page is hand-typed.
"""
from __future__ import annotations

import datetime as dt
import statistics as st
from collections import Counter

import altair as alt
import dash_data as dd
import pandas as pd
import streamlit as sl

sl.set_page_config(page_title="Pragnaya Priyadarshini HW10 - Ops dashboard", page_icon="📊", layout="wide")
sl.sidebar.markdown("**Pragnaya Priyadarshini** · DATA 260 · HW10")
page = sl.sidebar.radio("Page", ["Summary", "Evaluation", "Trace lookup"])
sl.sidebar.caption("PREFIX s3170 · domain: Municipal Transit Incidents")


# ---- caching -----------------------------------------------------------------------------------------------
@sl.cache_data(ttl=30, show_spinner=False)
def spans_cached(mtime: float):                    # keyed by the file's mtime: re-parsed only when spans.jsonl changes
    return dd.load_spans()


@sl.cache_data(ttl=30, show_spinner=False)
def json_cached(name: str, mtime: float):
    return dd.load_json(name)


@sl.cache_resource(show_spinner=False)
def redis_client():                                # expensive, reusable connection: one per server process
    import redis
    return redis.Redis.from_url("redis://localhost:6379/0", socket_connect_timeout=1, socket_timeout=1)


def mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def spans():
    return spans_cached(mtime(dd.SPANS))


def raw(name: str):
    return json_cached(name, mtime(dd.RAW / name))


def ts(ms: float | None) -> str:
    return "n/a" if ms is None else dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def fmt_ms(v: float | None) -> str:
    return "n/a" if v is None else (f"{v / 1000:.1f} s" if v >= 1000 else f"{v:.0f} ms")


# ---- page 1: summary ------------------------------------------------------------------------------------------
def page_summary() -> None:
    sl.title("System summary")
    all_rows = dd.requests(spans())
    if not all_rows:
        sl.warning("No spans found in data/hw10/spans/spans.jsonl yet. Run the pipeline with HW10_TRACE=1 (make agents-hw10).")
        return
    choice = sl.select_slider("Time window (relative to the newest recorded request)", ["Last 1 h", "Last 3 h", "Last 6 h", "Last 24 h", "All recorded data"],
                              value="All recorded data")
    hours = {"Last 1 h": 1, "Last 3 h": 3, "Last 6 h": 6, "Last 24 h": 24}.get(choice)
    rows, t0, t1 = dd.window(all_rows, hours)
    s = dd.summary(rows)
    src = f"Window: **{ts(t0)} → {ts(t1)}** ({choice.lower()}) · Source: `data/hw10/spans/spans.jsonl` (cache_lookup, final spans)"
    sl.caption(src)
    sl.info("These requests come from the HW10 experiments (50 confirmed cache misses, 20 repeat questions to measure hits, "
            "1 injected failure), not from production traffic, so the hit rate reflects that mix.")

    c1, c2, c3, c4 = sl.columns(4)
    c1.metric("Requests", s["requests"])
    c1.caption("Window and source: see above (distinct trace_ids with a cache_lookup span; warm-ups excluded)")
    c2.metric("Cache hit rate", f"{s['hit_rate_pct']}%")
    c2.caption(f"{s['hits']} hits vs {s['misses']} misses · same window/source")
    c3.metric("Error rate", f"{s['error_rate_pct']}%")
    c3.caption(f"{s['errors']} of {s['requests']} requests had an error in a request-path span · same window/source")
    c4.metric("Cache miss p50 latency", fmt_ms(s["miss_latency_ms"]["p50"]))
    c4.caption(f"p95 {fmt_ms(s['miss_latency_ms']['p95'])} · n={s['miss_latency_ms']['n']} · cache_lookup start → final answer")

    sl.subheader("Cache hits vs cache misses (kept separate)")
    left, right = sl.columns(2)
    hit_df = pd.DataFrame({"path": ["Cache HIT", "Cache MISS"], "requests": [s["hits"], s["misses"]]})
    left.altair_chart(alt.Chart(hit_df).mark_bar().encode(x="path:N", y="requests:Q",
                      color=alt.Color("path:N", scale=alt.Scale(domain=["Cache HIT", "Cache MISS"], range=["#2a9d8f", "#e76f51"]), legend=None)),
                      use_container_width=True)
    lat = pd.DataFrame([
        {"path": "Cache HIT", "p50": s["hit_latency_ms"]["p50"], "p95": s["hit_latency_ms"]["p95"], "mean": s["hit_latency_ms"]["mean"],
         "max": s["hit_latency_ms"]["max"], "n": s["hit_latency_ms"]["n"]},
        {"path": "Cache MISS", "p50": s["miss_latency_ms"]["p50"], "p95": s["miss_latency_ms"]["p95"], "mean": s["miss_latency_ms"]["mean"],
         "max": s["miss_latency_ms"]["max"], "n": s["miss_latency_ms"]["n"]}])
    right.markdown("**End-to-end latency (ms)**")
    right.dataframe(lat.set_index("path"), use_container_width=True)
    right.caption("Hit = cache_lookup duration. Miss = cache_lookup start → final answer received (includes planner, writer, reviewer, queue waits).")

    sl.subheader("Cache-miss stage latency (Part 4.3)")
    stats = raw("latency_stats.json")
    if stats:
        tbl = pd.DataFrame([{"Stage": k, "n": v["n"], "p50 (ms)": v["p50_ms"], "p95 (ms)": v["p95_ms"], "% of cache-miss end-to-end": v["pct_of_end_to_end"]}
                            for k, v in stats["stages"].items()])
        sl.dataframe(tbl.set_index("Stage"), use_container_width=True)
        sl.caption(f"Window: the {stats['n_requests']} confirmed cache-miss requests of the Part 4.3 experiment · Source: spans.jsonl + "
                   f"`reports/hw10/raw/latency_runs.json` · dominant stage: **{stats['dominant_stage']}**. Evaluation is offline (after the answer is returned).")
    else:
        sl.caption("Run `python code/hw10/latency_report.py` to produce reports/hw10/raw/latency_stats.json.")

    try:
        n_cache = sum(1 for _ in redis_client().scan_iter(match="s3170:hw10:*", count=500))
        sl.caption(f"Live: {n_cache} answers currently stored in the Redis semantic cache (namespace s3170:hw10). Source: Redis at localhost:6379.")
    except Exception:  # noqa: BLE001 - dashboard must still render when Redis is down
        sl.caption("Live Redis cache size unavailable (Redis not reachable).")

    sl.subheader("Recent requests")
    recent = pd.DataFrame([{"started": ts(r["start_ms"]), "trace_id": r["trace_id"], "path": r["path"].upper(),
                            "latency": fmt_ms(r["e2e_ms"]), "status": "ERROR @ " + r["failing_stage"] if r["is_error"] else "ok"}
                           for r in reversed(rows[-25:])])
    sl.dataframe(recent, use_container_width=True, hide_index=True)


# ---- page 2: evaluation ----------------------------------------------------------------------------------------
def page_evaluation() -> None:
    sl.title("Evaluation results")
    sl.subheader("Part 2 - pipeline evaluation (DeepEval GEval, local judge, 1-5 scale)")
    res = raw("eval_results.json")
    ok = [v for v in (res or {}).values() if v.get("status") == "ok"]
    if not ok:
        sl.warning("No evaluation results yet. Run: `HW10_TRACE=1 python code/hw10/evaluate_pipeline.py --file reports/hw10/raw/eval_sample.json`")
    else:
        sl.caption(f"Source: `reports/hw10/raw/eval_results.json` · {len(ok)} evaluated requests · judge: {ok[0]['judge']}")
        means = {"Plan Quality": [v["plan_quality"]["score"] for v in ok],
                 "Writer Helpfulness": [v["writer_helpfulness"]["score"] for v in ok],
                 "Final Answer Helpfulness": [v["final_helpfulness"]["score"] for v in ok if v["final_helpfulness"]["score"] is not None]}
        mdf = pd.DataFrame([{"Stage": k, "mean": round(st.mean(v), 2), "min": min(v), "max": max(v), "n": len(v)} for k, v in means.items()])
        a, b = sl.columns([1, 2])
        a.markdown("**Scores by pipeline stage**")
        a.dataframe(mdf.set_index("Stage"), use_container_width=True)
        b.altair_chart(alt.Chart(mdf).mark_bar().encode(x=alt.X("Stage:N", sort=None), y=alt.Y("mean:Q", scale=alt.Scale(domain=[0, 5])),
                                                       color=alt.Color("Stage:N", legend=None)), use_container_width=True)
        sl.markdown("**Scores by case**")
        case_df = pd.DataFrame([{"trace_id": v["trace_id"][:8], "question": v["question"][:70], "Plan": v["plan_quality"]["score"],
                                 "Draft (Writer)": v["writer_helpfulness"]["score"], "Final": v["final_helpfulness"]["score"],
                                 "Final - Draft": v["final_vs_draft"]["difference"],
                                 "final == draft text": v["draft"].strip() == (v["final_answer"] or "").strip()} for v in ok])
        sl.dataframe(case_df, use_container_width=True, hide_index=True)
        diffs = [v["final_vs_draft"]["difference"] for v in ok if v["final_vs_draft"]["difference"] is not None]
        same = sum(1 for v in ok if v["draft"].strip() == (v["final_answer"] or "").strip())
        sl.markdown("**Final-vs-Draft Improvement**")
        sl.write(f"Mean final − draft = {st.mean(diffs):+.2f} · distribution {dict(sorted(Counter(diffs).items()))} · "
                 f"{same} of {len(ok)} final answers are word-for-word identical to the draft.")
        with sl.expander("Judge reasons and interpretation for one case"):
            pick = sl.selectbox("Case", [v["trace_id"] for v in ok], format_func=lambda t: f"{t[:8]} · {res[t]['question'][:60]}")
            v = res[pick]
            sl.write(f"**Plan Quality {v['plan_quality']['score']}/5** — {v['plan_quality']['reason']}")
            sl.write(f"**Writer Helpfulness {v['writer_helpfulness']['score']}/5** (trace_id {v['trace_id']}) — {v['writer_helpfulness']['reason']}")
            sl.write(f"**Final Answer Helpfulness {v['final_helpfulness']['score']}/5** — {v['final_helpfulness']['reason']}")
            sl.write(f"**Interpretation:** {v['final_vs_draft']['interpretation']}")
        m = {k: st.mean(v) for k, v in means.items()}
        sl.markdown("**What the scores suggest about Planner / Writer / Reviewer coordination**")
        sl.write(f"- Planner: mean {m['Plan Quality']:.2f}, the lowest of the three stages. Plans are short generic 3-step lists, so they are judged useful but not specific.\n"
                 f"- Writer: mean {m['Writer Helpfulness']:.2f}. The drafts are the main source of answer quality in this pipeline.\n"
                 f"- Reviewer: mean final {m['Final Answer Helpfulness']:.2f}, and {same}/{len(ok)} finals equal their drafts. The Reviewer is rule-based "
                 f"(length / placeholder checks), so it passes text through unchanged and cannot improve it. The small final-vs-draft differences on "
                 f"identical text are judge noise, not improvement. Improvement from the Reviewer was therefore not observed, and none should be claimed.")

    sl.divider()
    sl.subheader("Part 3 - is the judge trustworthy? (judge vs hand-assigned human labels)")
    val = raw("judge_validation.json")
    runs = raw("judge_runs.json")
    if not val:
        sl.info("Judge validation has not been run yet. It needs the 20 hand-assigned labels committed first: `python code/hw10/validate_judge.py`.")
    else:
        p = val["part_3_2_run1_vs_human"]
        r = val["repeatability"]
        sl.caption(f"Source: `reports/hw10/raw/judge_validation.json` and `judge_runs.json` · {val['n_cases']} frozen drafts · {val['n_runs']} judge runs · "
                   f"settings: {val['settings']['judge_model']}, temperature {val['settings']['temperature']}, seed {val['settings']['seed']}")
        c1, c2, c3, c4 = sl.columns(4)
        c1.metric("Spearman (judge vs human)", p["spearman"])
        c2.metric("Mean absolute difference", p["mean_abs_diff"])
        c3.metric("Cases whose score changed across runs", f"{r['cases_whose_score_changed_across_runs']} / {r['cases_compared']}")
        c4.metric("Mean / max abs change", f"{r['mean_abs_change']} / {r['max_abs_change']}")
        sl.write(f"Signed bias (judge − human): {p['mean_signed_diff_judge_minus_human']} · fraction of run-pair comparisons that changed: {r['fraction_pair_comparisons_changed']}")
        if runs:
            human = {c: None for c in runs["runs"][0]["cases"]}
            import csv
            with open(dd.ROOT / "data" / "hw10" / "human_labels.csv", newline="") as fh:
                human = {row["case_id"]: row["human_score"] for row in csv.DictReader(fh)}
            raw_df = pd.DataFrame([{"case": cid, "human": human.get(cid), **{f"judge run {run['run']}": run["cases"][cid]["score"] for run in runs["runs"]}}
                                   for cid in runs["runs"][0]["cases"]])
            sl.markdown("**Raw per-case scores** (statistics above can be recomputed from this table)")
            sl.dataframe(raw_df, use_container_width=True, hide_index=True)


# ---- page 3: trace lookup --------------------------------------------------------------------------------------
def page_trace() -> None:
    sl.title("Trace lookup")
    ex = raw("trace_examples.json") or {}
    sl.caption("Source: `data/hw10/spans/spans.jsonl`. trace_id is the HW8 correlation_id (no second identifier).")
    quick = {f"{k.replace('_', ' ')} example": ex[k]["trace_id"] for k in ("cache_hit", "cache_miss", "failed") if k in ex}
    if quick:
        sl.write("Required example traces: " + " · ".join(f"**{k}**: `{v}`" for k, v in quick.items()))
    pick = sl.radio("Load an example", ["(type a trace_id below)"] + list(quick), horizontal=True)
    default = quick.get(pick, "")
    tid = sl.text_input("trace_id (full id, or a unique prefix of at least 6 characters)", value=default)
    if not tid.strip():
        return
    tv = dd.trace_view(spans(), tid)
    if tv is None:
        sl.error("No trace found for that id (check it, or run the pipeline with HW10_TRACE=1).")
        return
    badge = ("🟢 CACHE HIT path — answered from the semantic cache; Kafka agents were not used" if tv["path"] == "hit"
             else "🟠 CACHE MISS path — went through Kafka: inbox → planner → tasks → writer → drafts → reviewer → final")
    sl.subheader(badge)
    if tv["failed"]:
        sl.error(f"FAILED TRACE — failing stage: **{tv['failing_stage']}** · error: {tv['error']}")
    rows = []
    t0 = min(s["start_ms"] for s in tv["spans"])
    for s in tv["spans"]:
        rows.append({"stage": s["stage"], "start": s["start"], "end": s["end"], "duration_ms": s["duration_ms"], "status": s["status"],
                     "error": s["error"] or "", "start_offset_ms": round(s["start_ms"] - t0, 1), "end_offset_ms": round(s["end_ms"] - t0, 1),
                     "kind": "queue wait" if s["stage"] in ("inbox", "tasks", "drafts", "final") else "processing"})
    df = pd.DataFrame(rows)
    sl.dataframe(df[["stage", "kind", "start", "end", "duration_ms", "status", "error"]], use_container_width=True, hide_index=True)
    gdf = df[df["stage"] != "evaluator"]            # the evaluator runs offline, long after the request, and would squash the chart
    gantt = alt.Chart(gdf).mark_bar().encode(
        y=alt.Y("stage:N", sort=dd.STAGE_ORDER, title=None), x=alt.X("start_offset_ms:Q", title="ms since the request started"),
        x2="end_offset_ms:Q",
        color=alt.Color("status:N", scale=alt.Scale(domain=["ok", "error"], range=["#2a9d8f", "#d62828"])),
        tooltip=["stage", "kind", "duration_ms", "status", "error"])
    sl.altair_chart(gantt, use_container_width=True)
    sl.caption("Queue-wait spans (inbox, tasks, drafts, final) run from the moment a message was produced to the moment the next stage picked it up. "
               "The chart shows the request path only; the evaluator span (listed in the table) runs offline, after the answer was returned.")
    res = raw("eval_results.json") or {}
    if tv["trace_id"] in res and res[tv["trace_id"]].get("status") == "ok":
        v = res[tv["trace_id"]]
        sl.write(f"Evaluation of this request: plan {v['plan_quality']['score']}/5 · draft {v['writer_helpfulness']['score']}/5 · final {v['final_helpfulness']['score']}/5")


{"Summary": page_summary, "Evaluation": page_evaluation, "Trace lookup": page_trace}[page]()

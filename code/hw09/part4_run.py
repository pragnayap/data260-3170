#!/usr/bin/env python3
"""HW9 Part 4 - self-improving two-agent system.

    python part4_run.py demo        4.1 controlled revision sequence
    python part4_run.py train       4.2 training stream: failures -> lessons -> reuse (writes lessons.json)
    python part4_run.py validate    4.3 gate every candidate lesson on validation_data.json
    python part4_run.py variants    4.4 test_data.json on the four variants
"""
from __future__ import annotations

import copy
import json
import statistics
import sys
from collections import Counter

from agents_si import (
    PART4,
    AnsweringAgent,
    EvaluatorAgent,
    LessonStore,
    load_reference,
    question_features,
    run_question,
)
from common import RAW, banner

LESSON_TEMPLATES = {
    "unsupported_answer": ("no_record",
        "The answer states a fact for a question that has no matching database record (answered from general knowledge).",
        "If the database says no record matched, do not answer from general knowledge. Reply that you do not have that information in the transit database."),
    "stale_value": ("changing_value",
        "The answer reports an outdated value for something that changes over time (an earlier fare).",
        "Fares change over time. When asked about a fare, report the fare with the LATEST effective date in fare_history, never an earlier one."),
    "missing_fact": ("multi_fact",
        "The answer omits one of the several facts the question asked for.",
        "When a question asks for more than one thing, state every requested fact explicitly in the answer (join them with 'and')."),
}
# Hand-written, deliberately OVER-BROAD candidate used to exercise the validation gate (documented as such in the report).
OVERBROAD = ("unsupported_answer", "always",
    "The answer states a fact for a question that has no matching database record (answered from general knowledge).",
    "Only answer questions that contain a route code in the form R-NNNN. For every other question, say you cannot answer it.")

LESSONS = PART4 / "lessons.json"


def load_questions(name: str) -> list[dict]:
    return json.loads((PART4 / f"{name}.json").read_text())


def dump(name: str, obj) -> None:
    (RAW / name).write_text(json.dumps(obj, indent=2, default=str))


def show(res: dict) -> None:
    for t in res["trace"]:
        print(f"    attempt {t['attempt']}: {t['answer']!r}\n      evaluator: {t['result']} - {t['explanation']}"
              + (f"\n      feedback: {t['feedback']}" if t["feedback"] else "")
              + (f"\n      lessons loaded: {t['lessons_loaded']}" if t["lessons_loaded"] else ""), flush=True)
    print(f"    => final {res['final_result']} after {res['attempts']} attempt(s), {res['latency_s']}s", flush=True)


# --- 4.1 -------------------------------------------------------------------------------------------------------
def demo() -> None:
    ref = load_reference()
    q = "Which agency operates route R-0110 and what type of route is it?"
    forced = "Route R-0110 is a Commuter Rail route."      # CONTROLLED FAULT: attempt 1 is intentionally incomplete (no agency)
    print(f"Question: {q}\nControlled fault: attempt 1 is forced to {forced!r}", flush=True)
    res = run_question(q, AnsweringAgent(ref), EvaluatorAgent(ref), repair=True, forced_first=forced)
    show(res)
    dump("part4_controlled_demo.json", res)


# --- 4.2 -------------------------------------------------------------------------------------------------------
def train() -> None:
    ref = load_reference()
    if LESSONS.exists():
        LESSONS.unlink()
    store = LessonStore(LESSONS)
    answerer, evaluator = AnsweringAgent(ref, store), EvaluatorAgent(ref)
    seen: Counter = Counter()
    log = []
    for item in load_questions("training_data"):
        q = item["question"]
        print(f"\n[{item['id']}] {q}\n    features={sorted(question_features(q, ref))}", flush=True)
        res = run_question(q, answerer, evaluator, repair=True)
        store.mark_used(answerer.last_lessons)                  # use_count is bumped when a lesson was loaded
        show(res)
        ftype = res["first_attempt_failure"]
        created = None
        if ftype:
            seen[ftype] += 1
            already = any(lesson["failure_type"] == ftype for lesson in store.lessons)
            if seen[ftype] >= 2 and not already and ftype in LESSON_TEMPLATES:     # a REPEATED failure pattern
                trig, pattern, correction = LESSON_TEMPLATES[ftype]
                created = store.add(ftype, pattern, correction, trig)
                print(f"    ** pattern '{ftype}' seen {seen[ftype]}x -> created {created['lesson_id']}", flush=True)
        log.append({"id": item["id"], **res, "lesson_created": created["lesson_id"] if created else None})
    store.add(*OVERBROAD[:1], correction=OVERBROAD[3], failure_pattern=OVERBROAD[2], trigger=OVERBROAD[1])
    print(f"\nlessons.json now holds {len(store.lessons)} candidate lessons (last one is the hand-written over-broad candidate)")
    dump("part4_training_run.json", {"first_attempt_failure_counts": dict(seen), "items": log})


# --- 4.3 -------------------------------------------------------------------------------------------------------
def eval_set(items, ref, store, allowed_ids, tag) -> dict[str, dict]:
    answerer, evaluator = AnsweringAgent(ref, store, allowed_ids), EvaluatorAgent(ref)
    out = {}
    for it in items:
        res = run_question(it["question"], answerer, evaluator, repair=True)
        out[it["id"]] = {"question": it["question"], "first_ok": res["trace"][0]["result"] == "PASS", "final_ok": res["correct"],
                         "first_answer": res["trace"][0]["answer"], "final_answer": res["final_answer"], "attempts": res["attempts"],
                         "lessons_loaded": res["trace"][0]["lessons_loaded"]}
        print(f"  [{tag}] {it['id']}: first={'ok' if out[it['id']]['first_ok'] else 'FAIL'} final={'ok' if res['correct'] else 'FAIL'} "
              f"lessons={out[it['id']]['lessons_loaded']}", flush=True)
    return out


def validate() -> None:
    ref = load_reference()
    store = LessonStore(LESSONS, persist=True)
    items = load_questions("validation_data")
    kept: list[str] = []
    print("--- validation BEFORE any lesson ---", flush=True)
    before = eval_set(items, ref, store, set(), "before")
    report = []
    for lesson in list(store.lessons):
        print(f"\n--- candidate {lesson['lesson_id']} ({lesson['failure_type']}, trigger={lesson['trigger']}): {lesson['correction']}", flush=True)
        after = eval_set(items, ref, store, set(kept) | {lesson["lesson_id"]}, lesson["lesson_id"])
        reg_first = [k for k in before if before[k]["first_ok"] and not after[k]["first_ok"]]
        reg_final = [k for k in before if before[k]["final_ok"] and not after[k]["final_ok"]]
        fixed_first = [k for k in before if not before[k]["first_ok"] and after[k]["first_ok"]]
        fixed_final = [k for k in before if not before[k]["final_ok"] and after[k]["final_ok"]]
        unrelated = [k for k, v in after.items() if "no_record" in question_features(v["question"], ref) and not v["final_ok"]]
        keep = not reg_first and not reg_final and not unrelated and bool(fixed_first or fixed_final)
        note = (f"fixed(first/final)={len(fixed_first)}/{len(fixed_final)} regressed(first/final)={len(reg_first)}/{len(reg_final)} "
                f"unsupported-answers-on-unrelated={len(unrelated)}")
        print(f"  => {'KEEP' if keep else 'REJECT'}  {note}", flush=True)
        store.set_status(lesson["lesson_id"], "kept" if keep else "rejected", note)
        if keep:
            kept.append(lesson["lesson_id"])
            before = after                                       # the new baseline is the system WITH the kept lessons
        report.append({"lesson_id": lesson["lesson_id"], "decision": "kept" if keep else "rejected", "note": note,
                       "fixed_first": fixed_first, "fixed_final": fixed_final, "regressed_first": reg_first,
                       "regressed_final": reg_final, "unsupported_on_unrelated": unrelated})
    dump("part4_validation.json", {"kept": kept, "candidates": report})
    print(f"\nkept lessons: {kept}")


# --- 4.4 -------------------------------------------------------------------------------------------------------
def variants() -> None:
    ref = load_reference()
    store = LessonStore(LESSONS, persist=False)             # read-only copy: variant runs must not edit lessons.json
    kept = {lesson["lesson_id"] for lesson in store.lessons if lesson["status"] == "kept"}
    every = {lesson["lesson_id"] for lesson in store.lessons}
    spec = [("Baseline", False, None, None),
            ("Evaluator Repair", True, None, None),
            ("Lesson Memory", True, store, every),            # saves + reloads every lesson, no validation
            ("Validated Improvement", True, store, kept)]     # only lessons that passed the validation gate
    test = load_questions("test_data")
    summary, detail = [], {}
    for name, repair, st, allowed in spec:
        print(f"\n===== {name} =====", flush=True)
        answerer = AnsweringAgent(ref, st, allowed if st else None)
        evaluator = EvaluatorAgent(ref)
        results = []
        for it in test:
            st_copy = copy.deepcopy(st.lessons) if st else None
            res = run_question(it["question"], answerer, evaluator, repair=repair)
            if st:
                st.lessons = st_copy                          # discard use_count bumps
            results.append({"id": it["id"], **res})
            print(f"  {it['id']}: {res['final_result']} attempts={res['attempts']} {res['latency_s']}s  {res['final_answer'][:90]!r}", flush=True)
        ok = sum(r["correct"] for r in results)
        summary.append({"variant": name, "correct": ok, "incorrect": len(results) - ok,
                        "avg_attempts": round(statistics.mean(r["attempts"] for r in results), 2),
                        "avg_latency_s": round(statistics.mean(r["latency_s"] for r in results), 1),
                        "lessons_available": sorted(allowed) if allowed else []})
        detail[name] = results
        print(f"  -> {summary[-1]}", flush=True)
    dump("part4_variants.json", {"summary": summary, "detail": detail})
    print("\nVariant                 Correct  Incorrect  AvgAttempts  AvgLatency(s)")
    for s in summary:
        print(f"{s['variant']:<23} {s['correct']:>7}  {s['incorrect']:>9}  {s['avg_attempts']:>11}  {s['avg_latency_s']:>12}")


if __name__ == "__main__":
    banner(f"part4_run.py {' '.join(sys.argv[1:])}")
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("demo", demo), ("train", train), ("validate", validate), ("variants", variants)):
        if stage in (name, "all"):
            fn()

"""
HW9 Part 4 - Answering Agent, Evaluator Agent and the lesson store.

Agent communication (all in-process messages, nothing shared except these dicts):
    AnsweringAgent.answer(question, feedback=None, previous=None) -> answer text
    EvaluatorAgent.evaluate(question, answer)                      -> {result: PASS|REVISE, explanation, feedback,
                                                                       failure_type, facts_checked}
The Answering Agent never sees the evaluator's reference dataset; it only sees the route record(s) its own lookup
tool returns (and, on a retry, the evaluator's feedback). The Evaluator is deterministic: it checks the answer against
reference_dataset.json, which is the ground truth.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any

import common

PART4 = common.DATA / "part4"
REFERENCE = PART4 / "reference_dataset.json"
ROUTE_RE = re.compile(r"\bR-\d{4}\b")

# which reference fields a question asks about (keyword -> field). Used only by the EVALUATOR.
FIELD_KEYWORDS = [
    ("fare_current", ("fare", "ticket", "cost to ride", "single ride", "how much does it cost", "how much is a")),
    ("agency", ("agency", "operates", "operated by", "runs it", "which agency runs", "operator")),
    ("route_type", ("type of route", "route type", "kind of service", "what type")),
    ("route_name", ("name of route", "what is the name")),
    ("incident_count", ("how many incidents", "incidents are recorded", "how many incident")),
    ("riders_total", ("riders were affected", "riders affected", "how many riders")),
    ("top_incident_category", ("most common incident", "most frequent incident", "common incident category")),
]
REFUSAL = ("don't have", "do not have", "no information", "not available", "cannot", "can't", "unable", "outside",
           "no record", "no matching", "not in the", "no data", "doesn't exist", "does not exist", "not found", "couldn't find")


def load_reference() -> dict[str, dict[str, Any]]:
    data = json.loads(REFERENCE.read_text())["routes"]
    return {r["route_code"]: r for r in data}


def find_route(question: str, ref: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Route lookup shared by both agents: by code (R-NNNN), else by an exact route name that appears in the question."""
    for code in ROUTE_RE.findall(question):
        if code in ref:
            return ref[code]
    q = question.lower()
    for r in ref.values():
        if r["route_name"].lower() in q:
            return r
    return None


def question_features(question: str, ref: dict[str, dict[str, Any]]) -> set[str]:
    q = question.lower()
    feats = set()
    if find_route(question, ref) is None:
        feats.add("no_record")
    if any(k in q for k in FIELD_KEYWORDS[0][1]):
        feats.add("changing_value")
    if len(requested_fields(question)) >= 2:
        feats.add("multi_fact")
    return feats


def requested_fields(question: str) -> list[str]:
    q = question.lower()
    return [f for f, kws in FIELD_KEYWORDS if any(k in q for k in kws)]


def current_fare(r: dict[str, Any]) -> float:
    return max(r["fare_history"], key=lambda f: f["effective"])["fare_usd"]


def _norm(s: str) -> str:
    return s.lower().replace(",", "")


def _contains_number(answer: str, value: float | int) -> bool:
    a = _norm(answer)
    cands = {f"{value:.2f}", f"{value:g}"} if isinstance(value, float) else {str(value)}
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?!\d)", a) for c in cands)


# =========================================================================================================
class LessonStore:
    """lessons.json: lesson_id, failure_pattern, correction, created_at, use_count (+ trigger, failure_type, status)."""

    def __init__(self, path: Path, persist: bool = True):
        self.path, self.persist = Path(path), persist
        self.lessons: list[dict[str, Any]] = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self) -> None:
        if self.persist:
            self.path.write_text(json.dumps(self.lessons, indent=2))

    def add(self, failure_type: str, failure_pattern: str, correction: str, trigger: str, status: str = "candidate") -> dict[str, Any]:
        lesson = {"lesson_id": f"lesson_{len(self.lessons) + 1:03d}", "failure_pattern": failure_pattern,
                  "correction": correction, "created_at": dt.date.today().isoformat(), "use_count": 0,
                  "failure_type": failure_type, "trigger": trigger, "status": status}
        self.lessons.append(lesson)
        self.save()
        return lesson

    def set_status(self, lesson_id: str, status: str, note: str = "") -> None:
        for lesson in self.lessons:
            if lesson["lesson_id"] == lesson_id:
                lesson["status"] = status
                if note:
                    lesson["validation_note"] = note
        self.save()

    def relevant(self, features: set[str], allowed_ids: set[str] | None) -> list[dict[str, Any]]:
        """Lessons whose trigger matches the question's features (and whose id the current variant may load)."""
        return [lesson for lesson in self.lessons
                if (allowed_ids is None or lesson["lesson_id"] in allowed_ids)
                and (lesson["trigger"] == "always" or lesson["trigger"] in features)]

    def mark_used(self, lessons: list[dict[str, Any]]) -> None:
        for lesson in lessons:
            lesson["use_count"] += 1
        self.save()


# =========================================================================================================
class AnsweringAgent:
    """qwen3:8b through the HW8 llm.py adapter. Baseline prompt: short answer, no refusal rule, no lessons."""

    def __init__(self, ref: dict[str, dict[str, Any]], lessons: LessonStore | None = None,
                 allowed_ids: set[str] | None = None):
        self.ref, self.lessons, self.allowed_ids = ref, lessons, allowed_ids
        self.last_lessons: list[dict[str, Any]] = []

    @staticmethod
    def _card(r: dict[str, Any]) -> str:
        fares = "; ".join(f"${f['fare_usd']:.2f} effective {f['effective']}" for f in r["fare_history"])      # oldest first
        return (f"Route record {r['route_code']}: route_name={r['route_name']}; agency={r['agency']}; "
                f"route_type={r['route_type']}; incident_count={r['incident_count']}; total_riders_affected={r['riders_total']}; "
                f"most_common_incident_category={r['top_incident_category']}; fare_history (oldest first): {fares}")

    def answer(self, question: str, feedback: str | None = None, previous: str | None = None) -> str:
        from llm import complete
        r = find_route(question, self.ref)
        context = self._card(r) if r else "No database record matched the question."
        self.last_lessons = []
        lesson_block = ""
        if self.lessons is not None:                          # "load relevant lessons" BEFORE generating the answer
            self.last_lessons = self.lessons.relevant(question_features(question, self.ref), self.allowed_ids)
            if self.last_lessons:
                lesson_block = "Lessons learned from earlier mistakes (follow them):\n" + "\n".join(
                    f"- {lesson['correction']}" for lesson in self.last_lessons) + "\n"
        prompt = f"{lesson_block}Database:\n{context}\nQuestion: {question}\n"
        if feedback:
            prompt += f"Your previous answer was: {previous}\nEvaluator feedback: {feedback}\nWrite a corrected answer.\n"
        prompt += "Answer in one short sentence."
        return complete(prompt, max_tokens=90)


class EvaluatorAgent:
    """Checks an answer against the reference dataset. Returns PASS or REVISE with an explanation and feedback."""

    def __init__(self, ref: dict[str, dict[str, Any]]):
        self.ref = ref

    def evaluate(self, question: str, answer: str) -> dict[str, Any]:
        route = find_route(question, self.ref)
        a = answer.lower()
        if route is None:                                     # nothing in the ground truth supports an answer
            if any(p in a for p in REFUSAL):
                return self._pass("The question is not covered by the reference data and the answer says so.", [])
            return self._revise("unsupported_answer", "The reference data has no record for this question, but the answer states a fact anyway.",
                                "This is not covered by the transit database. Say you do not have that information instead of answering from general knowledge.", [])
        fields = requested_fields(question)
        missing, stale, checked = [], [], []
        for f in fields:
            if f == "fare_current":
                cur = current_fare(route)
                old = [x["fare_usd"] for x in route["fare_history"] if x["fare_usd"] != cur]
                ok = _contains_number(answer, cur)
                checked.append(f"fare_current={cur:.2f}")
                if not ok:
                    (stale if any(_contains_number(answer, o) for o in old) else missing).append(f)
            else:
                value = route[f]
                checked.append(f"{f}={value}")
                ok = _contains_number(answer, value) if isinstance(value, int) else _norm(str(value)) in _norm(answer)
                if not ok:
                    missing.append(f)
        if stale:
            return self._revise("stale_value", "The answer gives an outdated fare, not the current one.",
                                "That fare is out of date. The record lists fares with effective dates; use the one with the latest effective date.", checked)
        if missing:
            names = ", ".join(missing)
            return self._revise("missing_fact", f"The answer does not state the requested fact(s): {names}.",
                                f"Your answer is missing: {names}. Re-read the database record and state every requested fact explicitly.", checked)
        if not fields:
            return self._pass("No checkable fact was requested.", checked)
        return self._pass("All requested facts match the reference dataset.", checked)

    @staticmethod
    def _pass(why: str, checked: list[str]) -> dict[str, Any]:
        return {"result": "PASS", "explanation": why, "feedback": "", "failure_type": None, "facts_checked": checked}

    @staticmethod
    def _revise(ftype: str, why: str, feedback: str, checked: list[str]) -> dict[str, Any]:
        return {"result": "REVISE", "explanation": why, "feedback": feedback, "failure_type": ftype, "facts_checked": checked}


# =========================================================================================================
def run_question(question: str, answerer: AnsweringAgent, evaluator: EvaluatorAgent, repair: bool,
                 forced_first: str | None = None, max_attempts: int = 2) -> dict[str, Any]:
    """One question through the workflow. repair=False -> a single attempt (the Baseline). Stops after attempt 2."""
    t0 = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    answer, feedback, previous = "", None, None
    for n in range(1, (max_attempts if repair else 1) + 1):
        if n == 1 and forced_first is not None:
            answer = forced_first                              # controlled test case: a deliberately incomplete first answer
            lessons_loaded: list[str] = []
        else:
            answer = answerer.answer(question, feedback, previous)
            lessons_loaded = [lesson["lesson_id"] for lesson in answerer.last_lessons]
        verdict = evaluator.evaluate(question, answer)
        attempts.append({"attempt": n, "answer": answer, "lessons_loaded": lessons_loaded, **verdict})
        if verdict["result"] == "PASS":
            break
        feedback, previous = verdict["feedback"], answer
    final = attempts[-1]
    return {"question": question, "final_answer": final["answer"], "final_result": final["result"],
            "correct": final["result"] == "PASS", "attempts": len(attempts), "first_attempt_failure": attempts[0]["failure_type"],
            "latency_s": round(time.perf_counter() - t0, 2), "trace": attempts}

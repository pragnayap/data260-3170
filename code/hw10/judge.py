"""
HW10 Parts 2 and 3 - the LLM judge: DeepEval GEval on a LOCAL model.

Judge model  : qwen3:8b through Ollama (CPU), temperature 0, fixed seed (3170), thinking off, capped output.
Scale        : 1-5 everywhere (1 = very poor, 5 = excellent); GEval's rubric turns it into 0-1 internally and we convert back.
Steps        : fixed evaluation_steps (not regenerated per call) so every run of the judge sees exactly the same prompt.
Bounded      : every Ollama call has a client timeout and an output cap; a failed/malformed judge reply raises JudgeError
               after MAX_TRIES attempts and the caller records the case as an error. Nothing can hang a run.
"""
from __future__ import annotations

import os
import time
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")

import ollama  # noqa: E402
from deepeval.metrics import GEval  # noqa: E402
from deepeval.metrics.g_eval.utils import Rubric  # noqa: E402
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

JUDGE_MODEL = os.environ.get("HW10_JUDGE_MODEL", "qwen3:8b")
SEED = 3170
TEMPERATURE = 0.0
NUM_PREDICT = 400            # cap on the judge's reply (reason + score)
CLIENT_TIMEOUT = 150         # seconds per Ollama call
MAX_TRIES = 2                # per metric call


class JudgeError(RuntimeError):
    pass


class LocalJudge(DeepEvalBaseLLM):
    """DeepEval custom model: structured JSON replies from a local Ollama model."""

    def __init__(self, model: str = JUDGE_MODEL):
        self.model_name = model
        self.client = ollama.Client(timeout=CLIENT_TIMEOUT)
        self.calls = 0
        self.seconds = 0.0

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema=None, **_: Any):
        t0 = time.perf_counter()
        last: Exception | None = None
        for _attempt in range(MAX_TRIES):
            try:
                resp = self.client.chat(
                    model=self.model_name, messages=[{"role": "user", "content": prompt}],
                    format=schema.model_json_schema() if schema is not None else None, think=False,
                    options={"temperature": TEMPERATURE, "seed": SEED, "num_predict": NUM_PREDICT})
                text = resp.message.content or ""
                self.calls += 1
                self.seconds += time.perf_counter() - t0
                return schema.model_validate_json(text) if schema is not None else text
            except Exception as exc:  # noqa: BLE001 - timeout, connection error or malformed JSON: retry once, then give up
                last = exc
        raise JudgeError(f"judge unavailable or reply malformed after {MAX_TRIES} tries: {type(last).__name__}: {last}")

    async def a_generate(self, prompt: str, schema=None, **kw: Any):
        return self.generate(prompt, schema, **kw)

    def get_model_name(self) -> str:
        return f"{self.model_name} (Ollama, temperature {TEMPERATURE}, seed {SEED}, thinking off, num_predict {NUM_PREDICT})"


SCALE = [Rubric(score_range=(1, 1), expected_outcome="Very poor: wrong, irrelevant, or useless."),
         Rubric(score_range=(2, 2), expected_outcome="Poor: mostly unhelpful, with major gaps or errors."),
         Rubric(score_range=(3, 3), expected_outcome="Fair: partly helpful but vague, incomplete, or partly inaccurate."),
         Rubric(score_range=(4, 4), expected_outcome="Good: helpful, accurate and relevant with only minor gaps."),
         Rubric(score_range=(5, 5), expected_outcome="Excellent: accurate, specific, complete and directly useful.")]

HELPFULNESS_STEPS = [
    "Read the question and decide what the person asking actually needs.",
    "Check whether the answer directly addresses that question and stays relevant to it.",
    "Check whether the content is accurate and does not state specific facts or numbers it could not know.",
    "Check whether the answer is specific and complete enough for the person to act on or understand.",
    "Choose the score from 1 (very poor) to 5 (excellent) that matches these checks.",
]
PLAN_STEPS = [
    "Read the question and decide what a good answer would have to cover.",
    "Check whether each plan step is relevant to the question and not generic filler.",
    "Check whether the steps are specific, ordered sensibly and together cover what the question needs.",
    "Choose the score from 1 (very poor) to 5 (excellent) that matches these checks.",
]


def _metric(name: str, steps: list[str], judge: LocalJudge, params) -> GEval:
    return GEval(name=name, evaluation_steps=steps, evaluation_params=params, rubric=SCALE, model=judge,
                 async_mode=False, verbose_mode=False, threshold=0.5)


def make_metrics(judge: LocalJudge) -> dict[str, GEval]:
    io = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]
    return {"plan_quality": _metric("Plan Quality", PLAN_STEPS, judge, io),
            "writer_helpfulness": _metric("Writer Helpfulness", HELPFULNESS_STEPS, judge, io),
            "final_helpfulness": _metric("Final Answer Helpfulness", HELPFULNESS_STEPS, judge, io)}


def score(metric: GEval, question: str, output: str) -> tuple[int, str]:
    """One judge call -> (integer 1-5, short reason). Raises JudgeError if the judge cannot answer."""
    case = LLMTestCase(input=question, actual_output=output)
    try:
        normalised = metric.measure(case, _show_indicator=False)
    except JudgeError:
        raise
    except Exception as exc:  # noqa: BLE001 - DeepEval wraps judge failures; surface them uniformly
        raise JudgeError(f"{type(exc).__name__}: {exc}") from exc
    raw = int(round(float(normalised) * 4 + 1))          # (raw - 1) / 4  ->  raw
    return max(1, min(5, raw)), str(metric.reason or "")

"""Load memory_probes.yaml and score a reply against one probe (mechanical, no LLM judge)."""

import re
from pathlib import Path

import yaml

PROBES_PATH = Path(__file__).resolve().parents[2] / "memory_probes.yaml"


def load_probes(path: Path = PROBES_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def score_reply(reply: str, probe: dict, refusal_patterns: list[str]) -> dict:
    """Score = 1 + 4 * matched/total elements; forced to 1 if the reply is a refusal."""
    matched = {
        el["name"]: any(re.search(p, reply, flags=re.I) for p in el["any"]) for el in probe["elements"]
    }
    refused = any(re.search(p, reply, flags=re.I) for p in refusal_patterns)
    frac = sum(matched.values()) / len(matched)
    score = 1.0 if refused else round(1 + 4 * frac, 2)
    return {"probe": probe["id"], "score": score, "matched": matched, "refused": refused}

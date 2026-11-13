"""HW10 shared constants and helpers.

Named common10 (not common) on purpose: HW9's semantic_cache.py and qa_agent.py do `import common` and must keep
getting HW9's common.py. Importing this module puts hw09, web_application and hw08 on sys.path first.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HW09 = ROOT / "code" / "hw09"
HW08 = ROOT / "code" / "hw08"
WEBAPP = ROOT / "code" / "web_application"
for _p in (WEBAPP, HW08, HW09):                 # HW09 ends up first, so `import common` resolves to HW9's file
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PREFIX = "s3170"
SEED = 3170
DATA = ROOT / "data" / "hw10"
RAW = ROOT / "reports" / "hw10" / "raw"
SPANS = DATA / "spans" / "spans.jsonl"
for _d in (DATA, RAW, SPANS.parent):
    _d.mkdir(parents=True, exist_ok=True)

# The judge and the pipeline both use the HW8 local-model adapter (qwen3:8b via Ollama, CPU).
CACHE_NAMESPACE = "hw10"
SHIPPED_THRESHOLD = 0.95                        # the threshold HW9 chose to ship


def banner(label: str) -> None:
    """Student name in every terminal screenshot."""
    print(f"Pragnaya Priyadarshini HW10 - {label}", flush=True)

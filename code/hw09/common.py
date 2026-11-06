"""HW9 shared constants and helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBAPP = ROOT / "code" / "web_application"
HW08 = ROOT / "code" / "hw08"
for _p in (WEBAPP, HW08):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PREFIX = "s3170"
SEED = 3170
DATA = ROOT / "data" / "hw09"
RAW = ROOT / "reports" / "hw09" / "raw"
RAW.mkdir(parents=True, exist_ok=True)


def banner(label: str) -> None:
    """Student name in every terminal screenshot."""
    print(f"Pragnaya Priyadarshini HW9 - {label}", flush=True)

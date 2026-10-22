#!/usr/bin/env python3
"""
HW7 Part 4.IV - freeze the pricing page used by each acceptance run.

Fetches the live official page, extracts its text exactly as policy_retriever would,
and saves text + {url, accessed_at, sha256, rules_found} per scenario. Runs then load
the frozen text (tools.SNAPSHOTS), so a later change to the public page cannot change
the evidence.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import costs  # noqa: E402
import tools  # noqa: E402

URL = "https://capitalbikeshare.com/pricing"
OUT = Path(__file__).resolve().parents[3] / "reports" / "hw07" / "raw" / "pricing_snapshots"


def take(scenario: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    tools.SNAPSHOTS.pop(URL, None)
    text = tools.fetch_text(URL)
    meta = {"scenario": scenario, "source_url": URL,
            "accessed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "sha256": tools.sha256_text(text), "chars": len(text),
            "rules_found": costs.rules_found_in(text)}
    (OUT / f"{scenario}.txt").write_text(text)
    (OUT / f"{scenario}.json").write_text(json.dumps(meta, indent=2))
    return meta


def load(scenario: str) -> dict:
    """Return the saved metadata and register the frozen text for tools.fetch_text."""
    meta = json.loads((OUT / f"{scenario}.json").read_text())
    text = (OUT / f"{scenario}.txt").read_text()
    assert tools.sha256_text(text) == meta["sha256"], "snapshot text no longer matches its hash"
    tools.SNAPSHOTS[meta["source_url"]] = text
    return meta


if __name__ == "__main__":
    for s in ("membership_wins", "pay_per_use_wins"):
        m = take(s)
        print(s, m["sha256"], m["accessed_at"], all(m["rules_found"].values()), m["rules_found"])


def freeze(url: str, tag: str) -> dict:
    """Capture `url` now, save it under `tag`, and pin it for the run that follows."""
    tools.SNAPSHOTS.pop(url, None)
    text = tools.fetch_text(url)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"scenario": tag, "source_url": url,
            "accessed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "sha256": tools.sha256_text(text), "chars": len(text),
            "rules_found": costs.rules_found_in(text)}
    (OUT / f"{tag}.txt").write_text(text)
    (OUT / f"{tag}.json").write_text(json.dumps(meta, indent=2))
    tools.SNAPSHOTS[url] = text
    return meta

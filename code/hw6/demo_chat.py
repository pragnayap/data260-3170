"""
HW6 Part 2 evidence run: 12 messages in one session against the live API, then GET /api/memory
and GET /api/aggregate. Prints a banner with the student's name (required in terminal screenshots)
and saves everything to reports/hw06/raw/demo_*.json.

    python -u code/hw6/demo_chat.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

API = "http://localhost:8470"
RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"
USER, SESSION = "lucky_demo", "demo_session_1"
MESSAGES = [
    "Hi, I'm Lucky. I take the Line 22 bus from Downtown Transit Center every morning.",
    "I always bring my folding bike, so a working bike rack matters to me.",
    "Please email me at lucky.rider@example.com, not text messages.",
    "Last Friday the elevators at Civic Center Station on the BART Red Line were out all morning.",
    "Is that a mechanical failure or a safety hazard?",
    "What should I put in the description of the report?",
    "Yesterday my bus arrived twenty minutes late. Is that a delay?",
    "How long does the agency take to respond?",
    "Can I attach a photo to the report?",
    "What happens after a report is marked Investigating?",
    "Which route do I usually ride, and where do I board it?",
    "How should you contact me about my reports?",
]


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("DATA 260 HW6 - memory chat demo     Student: Pragnaya Priyadarshini (Lucky)")
    print(f"{datetime.now().isoformat(timespec='seconds')}   user_id={USER}   session_id={SESSION}")
    print("=" * 72, flush=True)
    transcript = []
    with httpx.Client(timeout=900) as c:
        for i, text in enumerate(MESSAGES, 1):
            r = c.post(f"{API}/api/chat", json={"user_id": USER, "session_id": SESSION, "message": text, "short_term_n": 6,
                                                "summarize_every": 4, "run_label": "demo"})
            r.raise_for_status()
            d = r.json()
            mu = d["memory_used"]
            transcript.append({"turn": i, "user": text, **d})
            print(f"\n[{i:>2}] You: {text}\n     Assistant: {d['reply']}")
            print(f"     memory used -> window={mu['short_term_count']} msgs, "
                  f"episodic={len(mu['episodic_facts'])}, session_summary={'yes' if mu['session_summary'] else 'no'}, "
                  f"lifetime_summary={'yes' if mu['long_term_summary'] else 'no'}", flush=True)
        mem = c.get(f"{API}/api/memory/{USER}").json()
        agg = c.get(f"{API}/api/aggregate/{USER}").json()
    (RAW / "demo_transcript.json").write_text(json.dumps(transcript, indent=2))
    (RAW / "demo_memory.json").write_text(json.dumps(mem, indent=2))
    (RAW / "demo_aggregate.json").write_text(json.dumps(agg, indent=2))
    print(f"\nsaved demo_transcript.json, demo_memory.json, demo_aggregate.json in {RAW}")
    print(f"messages stored: {len(mem['messages'])} (last 16), episodes: {len(mem['episodes'])}, "
          f"daily counts: {agg['daily_message_counts']}")


if __name__ == "__main__":
    main()

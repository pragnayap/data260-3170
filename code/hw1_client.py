"""
Part 4 - Small CLI demo of the model_client adapter.

Loads AGENT.md as the system prompt (strict bullet-only code review),
then runs an interactive chat loop through ModelClient.complete().

Commands:
  /stats  - print turn count, cumulative tokens, and history length
            (does not alter the conversation history)
  /exit   - quit (prints cumulative token summary)

Usage:
    python hw1_client.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from model_client import ModelClient  # noqa: E402

AGENT_MD_PATH = Path(__file__).resolve().parent.parent / "AGENT.md"


def main():
    client = ModelClient()
    history = []

    if AGENT_MD_PATH.exists():
        history.append({"role": "system", "content": AGENT_MD_PATH.read_text().strip()})

    print("Type your message, '/stats' for stats, or '/exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/stats":
            print(f"[stats] {client.stats(history)}")
            continue

        history.append({"role": "user", "content": user_input})
        reply = client.complete(history)
        history.append({"role": "assistant", "content": reply})
        print(f"Assistant: {reply}\n")

    client.print_exit_summary()


if __name__ == "__main__":
    main()

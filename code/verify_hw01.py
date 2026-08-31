"""
Self-check script for HW1 (Part 0 of submission).

Confirms the required files exist, the Python modules import/compile
cleanly, Ollama is reachable, and the non-determinism experiment produced
the expected number of raw records. Writes results to
reports/hw01/verification.json.

Usage:
    python verify_hw01.py
"""

import json
import py_compile
import sys
import urllib.request
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
REPORTS_DIR = REPO_ROOT / "reports" / "hw01"

checks = []


def check(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def file_exists(path: Path, label: str):
    exists = path.exists()
    check(f"file_exists:{label}", exists, str(path))
    return exists


def compiles(path: Path, label: str):
    if not path.exists():
        check(f"compiles:{label}", False, "file missing")
        return False
    try:
        py_compile.compile(str(path), doraise=True)
        check(f"compiles:{label}", True)
        return True
    except py_compile.PyCompileError as e:
        check(f"compiles:{label}", False, str(e))
        return False


def main():
    # --- Part I/II: web app ---
    file_exists(CODE_DIR / "web_application" / "HW1-PragnayaPriyadarshini.html", "html")
    file_exists(CODE_DIR / "web_application" / "hw1.js", "hw1_js")
    file_exists(REPO_ROOT / "DOMAIN_SCHEMA.md", "domain_schema")

    # --- Deployment ---
    file_exists(CODE_DIR / "Dockerfile", "dockerfile")

    # --- Part 2: agentic AI ---
    compiles(CODE_DIR / "agents_demo.py", "agents_demo")

    # --- Part 3: non-determinism experiment ---
    input_path = REPORTS_DIR / "cases" / "nondeterminism_input.json"
    if file_exists(input_path, "nondeterminism_input"):
        try:
            data = json.loads(input_path.read_text())
            check("nondeterminism_input:has_title_content", "title" in data and "content" in data)
        except Exception as e:
            check("nondeterminism_input:valid_json", False, str(e))

    raw_path = REPORTS_DIR / "raw" / "nondeterminism_raw.json"
    if file_exists(raw_path, "nondeterminism_raw"):
        try:
            records = json.loads(raw_path.read_text())
            check("nondeterminism_raw:40_records", len(records) == 40, f"found {len(records)}")
        except Exception as e:
            check("nondeterminism_raw:valid_json", False, str(e))

    file_exists(REPORTS_DIR / "raw" / "nondeterminism_summary.json", "nondeterminism_summary")
    file_exists(REPORTS_DIR / "METRICS.md", "metrics_md")

    # --- Part 4: model client ---
    compiles(REPO_ROOT / "src" / "model_client.py", "model_client")
    compiles(CODE_DIR / "hw1_client.py", "hw1_client")
    file_exists(REPO_ROOT / "AGENT.md", "agent_md")

    # --- Ollama reachability (fast check, no generation) ---
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as resp:
            tags = json.loads(resp.read())
            model_names = [m["name"] for m in tags.get("models", [])]
            check("ollama:reachable", True)
            check("ollama:qwen3_8b_pulled", any("qwen3:8b" in m for m in model_names), str(model_names))
    except Exception as e:
        check("ollama:reachable", False, str(e))

    result = {
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
        "checks": checks,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "verification.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print(f"\nWritten to: {out_path}")

    sys.exit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

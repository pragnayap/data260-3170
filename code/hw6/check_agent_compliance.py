"""
HW6 Part 4.4 - generate one function with AGENT.md as the system prompt and verify it follows
the instructions in AGENT.md. A control run WITHOUT AGENT.md shows what the instructions changed.

Checks (each maps to a line of AGENT.md):
    snake_case_names     coding conventions: snake_case
    type_hints           coding conventions: type hints on every parameter and the return value
    docstring            coding conventions: a docstring on every function
    no_print             coding conventions: logging, not print()
    line_length_100      coding conventions: <= 100 chars
    no_eval_exec         prohibited: eval / exec
    no_hardcoded_secret  prohibited: hardcoded secrets
    has_test_function    testing: a test named test_<function_name>
    tests_pass           testing: the generated test actually passes under pytest

Writes reports/hw06/raw/agent_md_compliance.json and the generated code next to it.
"""

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import file_memory as fm  # noqa: E402
from file_memory_cli import default_llm  # noqa: E402

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw"
TASK = (
    "Write a Python function named normalize_route_id that takes a raw transit route string such as "
    "'  line   22 ' and returns the canonical form 'LINE 22' (upper-case, single spaces, no leading or "
    "trailing whitespace). Reject an empty or whitespace-only string by raising ValueError. "
    "Reply with the complete Python module in one ```python block and nothing else."
)
SNAKE = re.compile(r"^_?[a-z][a-z0-9_]*$")


def extract_code(reply: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", reply, flags=re.S)
    return (m.group(1) if m else reply).strip() + "\n"


def check(code: str, func: str = "normalize_route_id") -> dict:
    tree = ast.parse(code)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    non_test = [f for f in funcs if not f.name.startswith("test_")]
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    results = {
        "snake_case_names": all(SNAKE.match(f.name) for f in funcs),
        "type_hints": all(
            f.returns is not None and all(a.annotation is not None for a in f.args.args + f.args.kwonlyargs)
            for f in non_test),
        "docstring": all(ast.get_docstring(f) for f in non_test),
        "no_print": "print" not in called,
        "line_length_100": all(len(ln) <= 100 for ln in code.splitlines()),
        "no_eval_exec": not ({"eval", "exec"} & called),
        "no_hardcoded_secret": not re.search(r"(password|secret|api_key|token)\s*=\s*['\"]\w+", code, flags=re.I),
        "has_test_function": any(f.name == f"test_{func}" for f in funcs),
    }
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "generated_mod.py").write_text(code)
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "generated_mod.py"],
                           cwd=td, capture_output=True, text=True, timeout=120)
        results["tests_pass"] = p.returncode == 0
        results["_pytest_tail"] = (p.stdout + p.stderr).strip().splitlines()[-1:] 
    return results


RULES = {
    "has_test_function": "AGENT.md testing rule: every new function ships with a pytest test named test_<function_name> "
                         "covering at least one edge case. Add test_normalize_route_id (include the empty-input case) in the same module.",
    "tests_pass": "The pytest run did not pass: {tail}. Make the function and its test pass.",
    "docstring": "AGENT.md coding rule: every function needs a docstring.",
    "type_hints": "AGENT.md coding rule: type hints on every parameter and the return value.",
    "no_print": "AGENT.md coding rule: no print() calls; use logging.",
    "line_length_100": "AGENT.md coding rule: lines of 100 characters or fewer.",
    "snake_case_names": "AGENT.md coding rule: snake_case names.",
    "no_eval_exec": "AGENT.md prohibited actions: never use eval or exec.",
    "no_hardcoded_secret": "AGENT.md prohibited actions: never hardcode secrets.",
}


def repair_message(failed: list[str], res: dict) -> str:
    tail = " ".join(res.get("_pytest_tail", [])) or "no output"
    lines = [RULES[k].format(tail=tail) for k in failed]
    return ("An automated check of your module found these problems:\n- " + "\n- ".join(lines)
            + "\nReply with the complete corrected module in one ```python block.")


def run(label: str, system: str | None) -> dict:
    """Attempt 1 as asked; if any check fails, up to TWO repair rounds that quote the failures back."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": TASK}]
    attempts = []
    for n in (1, 2, 3):
        reply = default_llm(msgs)
        code = extract_code(reply)
        (RAW / f"generated_{label}_attempt{n}.py").write_text(code)
        res = check(code)
        failed = [k for k, v in res.items() if not k.startswith("_") and not v]
        passed = [k for k, v in res.items() if not k.startswith("_") and v]
        attempts.append({"attempt": n, "passed": passed, "failed": failed, "details": res})
        if not failed:
            break
        msgs = msgs + [{"role": "assistant", "content": reply},
                       {"role": "user", "content": repair_message(failed, res)}]
    last = attempts[-1]
    (RAW / f"generated_{label}.py").write_text((RAW / f"generated_{label}_attempt{last['attempt']}.py").read_text())
    return {"label": label, "attempts": attempts, "passed": last["passed"], "failed": last["failed"], "details": last["details"]}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    system = fm.build_system_prompt(fm.load_files())
    out = {"task": TASK, "with_agent_md": run("with_agent_md", system), "control_without_agent_md": run("control_without_agent_md", None)}
    (RAW / "agent_md_compliance.json").write_text(json.dumps(out, indent=2))
    for k in ("with_agent_md", "control_without_agent_md"):
        r = out[k]
        for at in r["attempts"]:
            print(f"{k} attempt {at['attempt']}: {len(at['passed'])}/{len(at['passed']) + len(at['failed'])} passed; failed={at['failed']}")


if __name__ == "__main__":
    main()

"""
HW7 Part 6 - file tools and a bash safety gate. Pure Python, no model needed.

Every file tool resolves its path through _resolve(), which refuses anything that
escapes the sandbox root, so tests (and the agent) can only touch a temp course
directory. bash() runs only what confirm_bash() allows.
"""

from __future__ import annotations

import difflib
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

# --- sandbox ---------------------------------------------------------------

_root: Path | None = None


def set_sandbox(path: str | Path) -> Path:
    """Pin every file tool to `path`. Must be called before any tool."""
    global _root
    _root = Path(path).resolve()
    _root.mkdir(parents=True, exist_ok=True)
    return _root


def _resolve(path: str) -> Path:
    if _root is None:
        raise RuntimeError("sandbox not set; call set_sandbox() first")
    p = (_root / path).resolve()
    if p != _root and _root not in p.parents:
        raise PermissionError(f"path escapes sandbox: {path}")
    return p


# --- file tools ------------------------------------------------------------


def read_file(path: str, max_lines: int | None = None) -> str:
    lines = _resolve(path).read_text().splitlines()
    shown = lines if max_lines is None else lines[:max_lines]
    out = "\n".join(shown)
    if len(shown) < len(lines):
        out += f"\n... [{len(lines) - len(shown)} more lines]"
    return out


def write_file(path: str, content: str) -> str:
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} chars to {path}"


def edit_file(path: str, old: str, new: str) -> str:
    """Replace the single occurrence of `old`; return a short unified diff."""
    p = _resolve(path)
    before = p.read_text()
    if before.count(old) != 1:
        return f"error: expected exactly 1 match for old text, found {before.count(old)}"
    after = before.replace(old, new)
    p.write_text(after)
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=1
    )
    return "\n".join(diff)


def glob_files(pattern: str) -> list[str]:
    return sorted(str(f.relative_to(_root)) for f in _resolve(".").glob(pattern) if f.is_file())


def search_in_files(pattern: str, file_pattern: str = "*") -> list[str]:
    """Regex search; returns 'relpath:lineno:line' for each match."""
    rx = re.compile(pattern)
    hits = []
    for f in sorted(_resolve(".").rglob("*")):
        if f.is_file() and fnmatch.fnmatch(f.name, file_pattern):
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f.relative_to(_root)}:{n}:{line.strip()}")
    return hits


# --- safety gate -----------------------------------------------------------

SAFE_PREFIXES = ("ls", "cat", "pwd", "echo", "git status", "git log", "git diff", "head", "tail",
                 "wc", "grep", "python --version")

_DESTRUCTIVE = {
    "recursive deletion": r"\brm\b[^;&|]*\s-[a-zA-Z]*[rR]|\brm\b[^;&|]*--recursive",
    "privilege escalation": r"\b(sudo|su|doas)\b",
    "permission/ownership change": r"\b(chmod|chown|chgrp)\b",
    "raw-device write": r"\bdd\b[^;&|]*\bof=/dev/|>\s*/dev/(sd|hd|nvme|disk|rdisk)",
    "filesystem creation": r"\bmkfs(\.\w+)?\b|\bnewfs\b|\bdiskutil\s+(erase|partition)",
    "redirection to root path": r">>?\s*/(?!tmp/|dev/null)",
}


def is_destructive(command: str) -> bool:
    return any(re.search(rx, command) for rx in _DESTRUCTIVE.values())


def _destructive_reason(command: str) -> str:
    return next(name for name, rx in _DESTRUCTIVE.items() if re.search(rx, command))


_SPLIT = re.compile(r"&&|\|\||[;|&\n]")
_SUBSHELL = re.compile(r"\$\(|`|<\(")


def _all_segments_safe(command: str) -> bool:
    """True only if no subshell is used and EVERY chained segment starts with a
    safe prefix as whole words ('ls' matches 'ls -la' but not 'lsof')."""
    if _SUBSHELL.search(command):
        return False
    for seg in filter(None, (x.strip() for x in _SPLIT.split(command))):
        if not any(seg == p or seg.startswith(p + " ") for p in SAFE_PREFIXES):
            return False
    return True


class Gate(NamedTuple):
    allowed: bool
    reason: str


def confirm_bash(command: str, auto_approve: bool = False, confirmed: bool = False) -> Gate:
    """Decide whether `command` may run.

    destructive -> blocked unless confirmed=True (auto_approve never overrides it)
    safe prefix -> allowed
    anything else -> allowed only with auto_approve=True
    """
    command = command.strip()
    if is_destructive(command):
        if confirmed:
            return Gate(True, "destructive, explicitly confirmed")
        return Gate(False, f"destructive ({_destructive_reason(command)}); needs confirmation")
    if _all_segments_safe(command):
        return Gate(True, "matches SAFE_PREFIXES")
    if auto_approve:
        return Gate(True, "not on allow-list; auto_approve")
    return Gate(False, "not on allow-list; needs approval")


def bash(command: str, auto_approve: bool = False, confirmed: bool = False, timeout: int = 10) -> str:
    gate = confirm_bash(command, auto_approve, confirmed)
    if not gate.allowed:
        return f"BLOCKED: {gate.reason}"
    r = subprocess.run(command, shell=True, cwd=_resolve("."), capture_output=True, text=True,
                       timeout=timeout)
    return (r.stdout + r.stderr).strip()

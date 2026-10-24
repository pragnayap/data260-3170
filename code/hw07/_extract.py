"""Source-excerpt helper for build_report.py: pulls functions out of the real files so the report's
code blocks are the code that ran, never a retyped copy."""

import ast
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def get(path: str, *names: str, strip_doc: bool = True) -> str:
    src = (REPO / path).read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    out = []
    for name in names:
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        seg = lines[start:node.end_lineno]
        body0 = node.body[0]
        if strip_doc and isinstance(body0, ast.Expr) and isinstance(getattr(body0, "value", None), ast.Constant) \
                and isinstance(body0.value.value, str):
            d0 = body0.lineno - 1 - start
            d1 = body0.end_lineno - start
            seg = seg[:d0] + seg[d1:]
        out.append("\n".join(seg))
    return "\n\n".join(out)


def between(path: str, start: str, end: str, include_end: bool = False) -> str:
    lines = (REPO / path).read_text().splitlines()
    i = next(k for k, ln in enumerate(lines) if start in ln)
    j = next(k for k in range(i + 1, len(lines)) if end in lines[k])
    seg = lines[i:j + (1 if include_end else 0)]
    return textwrap.dedent("\n".join(seg))


def const(path: str, name: str) -> str:
    """A module-level assignment (possibly multi-line), by target name."""
    src = (REPO / path).read_text()
    tree = ast.parse(src)
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return "\n".join(src.splitlines()[n.lineno - 1:n.end_lineno])
    raise KeyError(name)

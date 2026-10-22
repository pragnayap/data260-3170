"""
HW7 Part 4 - the three MRKL tools as pure functions with JSON schemas.

Every tool returns one common shape: {"success", "data"?, "error"?, "source"?, "ts"?}.
None of them raises.

    csv_sql           read-only SELECT over the uploaded trips (in-memory SQLite)
    policy_retriever  fetch a pricing page, extract text, return short quotable snippets
    calculator        whitelisted arithmetic, evaluated by an AST walk (no eval)

Part 5 hooks. DEFENSES holds the two switches the prompt-injection experiment flips:
    sql_guard     True  -> csv_sql accepts exactly one SELECT, whatever the model says
                  False -> the pre-defense behaviour: the SQL string is executed as given
    (the other switch, prompt_label, lives in agent.py where the prompt is built)
The default is hardened. Pre-defense runs set it False explicitly.
"""

from __future__ import annotations

import ast
import csv
import datetime as dt
import hashlib
import html
import io
import operator
import re
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

DEFENSES = {"sql_guard": True}
MAX_ROWS = 200

# policy_retriever fetches a URL the caller supplied, so it must not be a way to reach
# internal addresses: only the official host, or fixture files under FIXTURE_ROOT.
ALLOWED_HOSTS = {"capitalbikeshare.com", "www.capitalbikeshare.com"}
FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "reports" / "hw07" / "fixtures"

# --- JSON schemas (what the model is shown) ------------------------------------

SCHEMAS = {
    "csv_sql": {
        "name": "csv_sql",
        "description": "Run ONE read-only SELECT over the uploaded trips table `trips` "
                       "(columns: started_at, ended_at, duration_min, rideable_type, "
                       "member_type).",
        "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}},
                         "required": ["sql"]},
        "output_schema": {"type": "object", "properties": {
            "rows": {"type": "array", "items": {"type": "object"}},
            "row_count": {"type": "number"}, "source": {"const": "uploaded.csv"}}},
    },
    "policy_retriever": {
        "name": "policy_retriever",
        "description": "Fetch the pricing page at `url` and return the k most relevant "
                       "short snippets for `query` (prices, included minutes, surcharges).",
        "input_schema": {"type": "object", "properties": {
            "url": {"type": "string"}, "query": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 10}},
            "required": ["url", "query"]},
        "output_schema": {"type": "object", "properties": {"passages": {
            "type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"}, "source": {"type": "string"},
                "score": {"type": "number"}}}}}},
    },
    "calculator": {
        "name": "calculator",
        "description": "Evaluate an arithmetic expression using digits and + - * / ( ) . only.",
        "input_schema": {"type": "object", "properties": {
            "expression": {"type": "string", "pattern": r"^[0-9+\-*/().\s]+$"},
            "units": {"type": "string"}}, "required": ["expression"]},
        "output_schema": {"type": "object", "properties": {
            "value": {"type": "number"}, "units": {"type": "string"}}},
    },
}


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _ok(data, source=None):
    return {"success": True, "data": data, "source": source, "ts": _ts()}


def _fail(error, source=None):
    return {"success": False, "error": error, "source": source, "ts": _ts()}


# --- csv_sql ----------------------------------------------------------------------

_SELECT = re.compile(r"^\s*select\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|"
    r"reindex|truncate|begin|commit|rollback|savepoint|load_extension)\b", re.IGNORECASE)


def sql_is_single_select(sql: str) -> str | None:
    """None if `sql` is exactly one read-only SELECT, else the reason it is refused."""
    stripped = sql.strip().rstrip(";").strip()
    if not _SELECT.match(stripped):
        return "only a SELECT statement is allowed"
    if ";" in stripped:
        return "only one statement is allowed"
    if re.search(r"--|/\*", stripped):
        return "SQL comments are not allowed"
    bad = _FORBIDDEN.search(stripped)
    if bad:
        return f"forbidden keyword {bad.group(1).upper()!r}"
    return None


class TripDB:
    """The uploaded CSV, loaded into an in-memory SQLite table named `trips`."""

    COLUMNS = ("started_at", "ended_at", "duration_min", "rideable_type", "member_type")

    def __init__(self, csv_text: str):
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        reader = csv.DictReader(io.StringIO(csv_text))
        self.con.execute("CREATE TABLE trips (started_at TEXT, ended_at TEXT, "
                         "duration_min REAL, rideable_type TEXT, member_type TEXT)")
        rows = []
        for r in reader:
            rows.append((r.get("started_at"), r.get("ended_at"),
                         float(r["duration_min"]) if r.get("duration_min") else None,
                         r.get("rideable_type") or "classic_bike", r.get("member_type") or ""))
        self.con.executemany("INSERT INTO trips VALUES (?,?,?,?,?)", rows)
        self.con.commit()

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]


def csv_sql(db: TripDB, sql: str) -> dict:
    src = "uploaded.csv"
    if not isinstance(sql, str) or not sql.strip():
        return _fail("sql must be a non-empty string", src)
    if DEFENSES["sql_guard"]:
        reason = sql_is_single_select(sql)
        if reason:
            return _fail(f"refused: {reason}", src)
        # Belt and braces: even a SELECT runs on a read-only view of the connection.
        db.con.execute("PRAGMA query_only = ON")
    else:
        db.con.execute("PRAGMA query_only = OFF")
    try:
        cur = db.con.executescript(sql) if not DEFENSES["sql_guard"] and ";" in sql.strip(";") \
            else db.con.execute(sql)
        rows = cur.fetchmany(MAX_ROWS) if cur.description else []
        names = [d[0] for d in cur.description] if cur.description else []
        out = [dict(zip(names, r, strict=False)) for r in rows]
    except sqlite3.Error as exc:
        return _fail(f"sql error: {exc}", src)
    return _ok({"rows": out, "row_count": len(out), "source": src}, src)


# --- policy_retriever ---------------------------------------------------------------

SNAPSHOTS: dict[str, str] = {}   # url -> frozen page text; lets a run use saved evidence


def extract_text(raw_html: str) -> str:
    """Page HTML -> one line of text, table cells joined by ' | '."""
    t = re.sub(r"(?s)<(script|style|noscript).*?</\1>", " ", raw_html)
    t = re.sub(r"<[^>]+>", "\n", t)
    lines = [ln.strip() for ln in html.unescape(t).split("\n") if ln.strip()]
    return " | ".join(lines)


def fetch_text(url: str) -> str:
    if url in SNAPSHOTS:
        return SNAPSHOTS[url]
    if url.startswith("file://"):
        path = Path(url[7:]).resolve()
        if FIXTURE_ROOT.resolve() not in path.parents:
            raise ValueError("file:// is only allowed under the HW7 fixtures directory")
        raw = path.read_text(errors="ignore")
    elif url.startswith("https://"):
        if urllib.parse.urlparse(url).hostname not in ALLOWED_HOSTS:
            raise ValueError("host is not an allowed pricing source")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    else:
        raise ValueError("url must be https:// (official host) or an HW7 fixture file://")
    return extract_text(raw)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_WORD = re.compile(r"[a-z0-9$.%/]+")
_STOP = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "is", "are", "what", "how"}


def _passages(text: str, window: int = 45, stride: int = 25):
    words = text.split()
    for i in range(0, max(1, len(words) - window + stride), stride):
        yield " ".join(words[i:i + window])


def policy_retriever(url: str, query: str, k: int = 4) -> dict:
    if not isinstance(url, str) or not isinstance(query, str) or not query.strip():
        return _fail("url and query must be non-empty strings", url if isinstance(url, str) else None)
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 10:
        return _fail("k must be an integer between 1 and 10", url)
    try:
        text = fetch_text(url)
    except Exception as exc:  # noqa: BLE001 - tools never raise
        return _fail(f"could not fetch page: {type(exc).__name__}: {exc}", url)
    terms = {w for w in _WORD.findall(query.lower()) if w not in _STOP}
    scored = []
    for p in _passages(text):
        toks = set(_WORD.findall(p.lower()))
        hit = len(terms & toks) + 0.5 * sum("$" in t for t in toks) * bool(terms & toks)
        if hit:
            scored.append((hit / (1 + len(terms)), p))
    scored.sort(key=lambda s: -s[0])
    passages = [{"text": p[:320], "source": url, "score": round(s, 3)} for s, p in scored[:k]]
    return _ok({"passages": passages}, url)


# --- calculator ---------------------------------------------------------------------

_ALLOWED = re.compile(r"^[0-9+\-*/().\s]+$")
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    raise ValueError("unsupported expression")


def calculator(expression: str, units: str | None = None) -> dict:
    if not isinstance(expression, str) or not _ALLOWED.match(expression):
        return _fail("expression may only contain digits and + - * / ( ) . and spaces")
    if len(expression) > 200:
        return _fail("expression too long")
    try:
        value = _eval(ast.parse(expression.strip(), mode="eval"))
    except ZeroDivisionError:
        return _fail("division by zero")
    except (ValueError, SyntaxError, RecursionError):
        return _fail("could not evaluate expression")
    data = {"value": round(float(value), 6)}
    if units:
        data["units"] = units
    return _ok(data)

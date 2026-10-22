"""
HW7 Part 4 - deterministic reference costs for Capital Bikeshare.

The LLM agent orchestrates the tools and writes the justification; this module
recomputes the numbers independently from the CSV so a hallucinated figure is caught,
and so the results panel shows verified numbers next to the agent's own.

Rules, as published on capitalbikeshare.com/pricing (checked against the frozen page
text by `rules_found_in`, so a changed page fails loudly instead of silently):
    non-member single ride : $1 unlock + $0.15/min classic, $0.35/min e-bike
    member                 : free unlock; classic free for 45 min then $0.05/min;
                             e-bike $0.15/min
    membership             : $120/year  ->  $10/month when amortised (assumption)
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime

UNLOCK = 1.00
CLASSIC_PER_MIN, EBIKE_PER_MIN = 0.15, 0.35
MEMBER_FREE_MIN, MEMBER_CLASSIC_OVER, MEMBER_EBIKE_PER_MIN = 45, 0.05, 0.15
ANNUAL_FEE = 120.00
MONTHLY_FEE = ANNUAL_FEE / 12

RULE_PATTERNS = {
    "annual $120": r"\$120/year",
    "classic $0.15/min": r"\$0\.15/min",
    "ebike $0.35/min": r"\$0\.35/min",
    "45 free then $.05/min": r"45 mins free, then \$\.05/min",
    "unlock $1": r"Bike unlocks \| \$1\b",
}


def rules_found_in(page_text: str) -> dict[str, bool]:
    return {name: bool(re.search(rx, page_text)) for name, rx in RULE_PATTERNS.items()}


def _is_ebike(kind: str) -> bool:
    return "electric" in (kind or "")


def payg_cost(minutes: float, kind: str) -> float:
    return UNLOCK + minutes * (EBIKE_PER_MIN if _is_ebike(kind) else CLASSIC_PER_MIN)


def member_residual(minutes: float, kind: str) -> float:
    if _is_ebike(kind):
        return minutes * MEMBER_EBIKE_PER_MIN
    return max(0.0, minutes - MEMBER_FREE_MIN) * MEMBER_CLASSIC_OVER


def load_trips(csv_text: str) -> list[dict]:
    trips = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        trips.append({"start": datetime.fromisoformat(r["started_at"]),
                      "minutes": float(r["duration_min"]),
                      "kind": r.get("rideable_type") or "classic_bike"})
    return trips


def reference_costs(csv_text: str) -> dict:
    trips = load_trips(csv_text)
    n = len(trips)
    first, last = min(t["start"] for t in trips), max(t["start"] for t in trips)
    months = (last.year - first.year) * 12 + (last.month - first.month) + 1

    payg = sum(payg_cost(t["minutes"], t["kind"]) for t in trips)
    residual = sum(member_residual(t["minutes"], t["kind"]) for t in trips)
    member_total = MONTHLY_FEE * months + residual
    avg_payg = payg / n
    avg_min = sum(t["minutes"] for t in trips) / n

    weeks: dict[str, list] = defaultdict(list)
    for t in trips:
        y, w, _ = t["start"].isocalendar()
        weeks[f"{y}-W{w:02d}"].append(t)
    weekly = [{"week": k, "rides": len(v),
               "avg_minutes": round(sum(t["minutes"] for t in v) / len(v), 1),
               "pay_per_use_spend": round(sum(payg_cost(t["minutes"], t["kind"]) for t in v), 2),
               "member_residual": round(sum(member_residual(t["minutes"], t["kind"])
                                            for t in v), 2)}
              for k, v in sorted(weeks.items())]

    return {
        "rides": n, "first_trip": first.isoformat(sep=" "), "last_trip": last.isoformat(sep=" "),
        "months_spanned": months, "avg_minutes": round(avg_min, 2),
        "ebike_share": round(sum(_is_ebike(t["kind"]) for t in trips) / n, 3),
        "pay_per_use_total": round(payg, 2),
        "membership_fee_total": round(MONTHLY_FEE * months, 2),
        "membership_residual": round(residual, 2),
        "membership_total": round(member_total, 2),
        "decision": "Buy Monthly Membership" if member_total < payg else "Pay Per Ride/Minute",
        "actual_rides_per_month": round(n / months, 1),
        "break_even_rides_per_month": round(MONTHLY_FEE / avg_payg, 1),
        "actual_minutes_per_month": round(n * avg_min / months, 1),
        "break_even_minutes_per_month": round(MONTHLY_FEE / avg_payg * avg_min, 1),
        "weekly": weekly,
    }

"""Ranking Tool: ALL arithmetic, benchmarking, tie-breaking and ranking. Deterministic Python only.
No LLM output is used here except the already-validated criterion scores.

Formulas (per supplier s, criterion c with weight w_c, max score M_c, score x_sc):
    absolute_score_s  = sum_c (x_sc / M_c) * w_c                      (0-100 when weights sum to 100)
    benchmark_c       = max_s x_sc  over valid (non-imputed) scores
    gap_sc            = x_sc - benchmark_c                            (0 for the leader, otherwise < 0)
    relative_pct_sc   = x_sc / benchmark_c * 100                      (100 if benchmark_c == 0: all tied)
    PPI_s             = sum_c relative_pct_sc * w_c / sum_c w_c

Ranking: sort by (PPI desc, submission date asc, experience rating desc, supplier name asc), then
assign 1, 2, 3, ... PPI is rounded to SORT_PRECISION decimals for sorting only.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import config

TIE_BREAK_RULES = [
    "Higher Peer Performance Index (PPI)",
    "Earlier submission date",
    "Higher historical experience rating",
    "Supplier name in ascending (A-Z) order",
]


class CriteriaError(ValueError):
    """Active criteria are unusable (none active, or weights do not total 100%)."""


def validate_criteria(criteria: list[dict[str, Any]]) -> None:
    if not criteria:
        raise CriteriaError("No active evaluation criteria. Activate at least one criterion.")
    total = sum(float(c["weight"]) for c in criteria)
    if abs(total - config.WEIGHT_TOTAL) > config.WEIGHT_TOLERANCE:
        raise CriteriaError(
            f"Active criteria weights total {total:g}%, but they must total {config.WEIGHT_TOTAL:g}%.")


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _sort_key(s: dict[str, Any]) -> tuple:
    return (-round(s["ppi"], config.SORT_PRECISION), _as_date(s["submission_date"]),
            -float(s["experience_rating"]), s["supplier_name"].casefold(), s["supplier_name"])


def compute_benchmarks(criteria: list[dict[str, Any]], scorecards: list[dict[str, Any]]) -> dict[int, float]:
    """Highest valid score per criterion across all suppliers (imputed placeholders are not 'valid')."""
    bench: dict[int, float] = {}
    for c in criteria:
        valid = [r["score"] for sc in scorecards for r in sc["criteria"]
                 if r["criterion_id"] == c["criterion_id"] and r.get("status") != "imputed"]
        bench[c["criterion_id"]] = max(valid) if valid else 0.0
    return bench


def _deciding_rule(upper: dict[str, Any], lower: dict[str, Any]) -> str:
    """Explain why `upper` is ranked directly above `lower`."""
    if round(upper["ppi"], config.SORT_PRECISION) != round(lower["ppi"], config.SORT_PRECISION):
        return (f"decided by rule 1 (higher PPI): {upper['ppi']:.2f} vs {lower['ppi']:.2f}")
    du, dl = _as_date(upper["submission_date"]), _as_date(lower["submission_date"])
    if du != dl:
        return f"PPI tied at {upper['ppi']:.2f}; decided by rule 2 (earlier submission): {du} vs {dl}"
    eu, el = float(upper["experience_rating"]), float(lower["experience_rating"])
    if eu != el:
        return (f"PPI and submission date tied; decided by rule 3 (higher experience rating): "
                f"{eu:g} vs {el:g}")
    return "PPI, submission date and experience tied; decided by rule 4 (supplier name A-Z)"


def rank_suppliers(criteria: list[dict[str, Any]], suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    """
    suppliers: [{supplier_name, submission_date, experience_rating, scorecard: {...Scorecard dump...}}]
    Returns {"benchmarks": {...}, "suppliers": [ranked result dicts], "tie_break_explanations": [...]}
    """
    validate_criteria(criteria)
    total_w = sum(float(c["weight"]) for c in criteria)
    bench = compute_benchmarks(criteria, [s["scorecard"] for s in suppliers])

    results: list[dict[str, Any]] = []
    for s in suppliers:
        card = s["scorecard"]
        by_id = {r["criterion_id"]: r for r in card["criteria"]}
        rows, absolute, ppi = [], 0.0, 0.0
        for c in criteria:
            r = by_id[c["criterion_id"]]
            w, mx, x, b = float(c["weight"]), float(c["max_score"]), float(r["score"]), bench[c["criterion_id"]]
            weighted = x / mx * w
            rel = (x / b * 100.0) if b > 0 else 100.0
            absolute += weighted
            ppi += rel * w / total_w
            rows.append({
                "criterion_id": c["criterion_id"], "name": c["name"], "weight": w, "max_score": mx,
                "score": x, "status": r.get("status", "ok"),
                "benchmark": b, "gap": x - b, "relative_pct": rel,
                "weighted_contribution": weighted, "ppi_contribution": rel * w / total_w,
                "justification": r.get("justification", ""), "evidence": r.get("evidence", ""),
                "evidence_verified": r.get("evidence_verified"),
            })
        results.append({
            "supplier_name": s["supplier_name"],
            "submission_date": _as_date(s["submission_date"]).isoformat(),
            "experience_rating": float(s["experience_rating"]),
            "evaluation_status": card.get("evaluation_status", "ok"),
            "absolute_score": absolute, "ppi": ppi, "final_rank": 0,
            "criteria": rows, "risks": card.get("risks", []), "overall_summary": card.get("overall_summary", ""),
        })

    results.sort(key=_sort_key)
    for i, r in enumerate(results, start=1):
        r["final_rank"] = i

    explanations = [
        f"Rank {a['final_rank']} {a['supplier_name']} above rank {b['final_rank']} {b['supplier_name']}: "
        f"{_deciding_rule(a, b)}."
        for a, b in zip(results, results[1:])
    ]
    return {"benchmarks": {str(k): v for k, v in bench.items()}, "suppliers": results,
            "tie_break_explanations": explanations}

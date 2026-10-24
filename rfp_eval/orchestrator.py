"""Orchestrator Agent: runs the workflow and calls the tools in the required order.

    1 load active criteria  ->  2 per supplier: extract PDF -> build prompt -> LLM -> validate
    ->  3 rank (benchmarks, PPI, tie-breaks)  ->  4 persist under one RFP_RUN_ID  ->  5 return result

The LLM is only used in step 2 to judge proposal content. Everything numeric happens in ranking.py.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from . import config, db, prompts
from .llm import LLMClient, LLMError
from .pdf_tool import PDFExtractionError, extract_text
from .ranking import CriteriaError, TIE_BREAK_RULES, rank_suppliers, validate_criteria
from .validation import LLMOutputError, failed_scorecard, normalize_scorecard, parse_llm_json

ProgressFn = Callable[[float, str], None]


class EvaluationError(Exception):
    """The run could not produce a ranking (e.g. every supplier failed)."""


@dataclass
class SupplierInput:
    supplier_name: str
    submission_date: date
    experience_rating: float
    filename: str
    pdf_bytes: bytes


def validate_inputs(inputs: list[SupplierInput]) -> list[str]:
    """Return a list of blocking error messages (empty list = OK)."""
    errors: list[str] = []
    if len(inputs) < 2:
        errors.append("Upload at least two supplier PDFs - peer benchmarking needs more than one supplier.")
    seen: dict[str, str] = {}
    for s in inputs:
        name = (s.supplier_name or "").strip()
        label = s.filename
        if not name:
            errors.append(f"{label}: supplier name is required.")
        elif name.casefold() in seen:
            errors.append(f"{label}: supplier name '{name}' duplicates the one for {seen[name.casefold()]}.")
        else:
            seen[name.casefold()] = label
        if not isinstance(s.submission_date, date):
            errors.append(f"{label}: a valid submission date is required.")
        try:
            rating = float(s.experience_rating)
            if not config.EXPERIENCE_MIN <= rating <= config.EXPERIENCE_MAX:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{label}: experience rating must be a number between "
                          f"{config.EXPERIENCE_MIN:g} and {config.EXPERIENCE_MAX:g}.")
    return errors


def _new_run_id() -> str:
    return f"RFP-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"


def _evaluate_one(client: LLMClient, criteria: list[dict[str, Any]], s: SupplierInput,
                  trace: list[dict[str, str]], warnings: list[str]) -> dict[str, Any]:
    """Document Tool -> Evaluation Agent -> Validation Tool for one supplier. Never raises."""
    name = s.supplier_name.strip()
    try:
        doc = extract_text(s.pdf_bytes)
    except PDFExtractionError as exc:
        warnings.append(f"[{name}] {exc}")
        trace.append({"tool": "document_tool", "supplier": name, "detail": f"FAILED: {exc}"})
        return failed_scorecard(criteria, name, str(exc)).model_dump()
    warnings.extend(f"[{name}] {w}" for w in doc.warnings)
    trace.append({"tool": "document_tool", "supplier": name,
                  "detail": f"extracted {doc.chars:,} characters from {doc.pages} page(s)"})

    retry_note = None
    for attempt in range(1, config.MAX_LLM_ATTEMPTS + 1):
        user_prompt = prompts.build_user_prompt(name, criteria, doc.text, retry_note)
        try:
            raw = client.complete(prompts.SYSTEM_PROMPT, user_prompt)
        except LLMError as exc:
            warnings.append(f"[{name}] LLM call failed: {exc}")
            trace.append({"tool": "evaluation_agent", "supplier": name, "detail": f"FAILED: {exc}"})
            return failed_scorecard(criteria, name, str(exc)).model_dump()
        trace.append({"tool": "evaluation_agent", "supplier": name,
                      "detail": f"attempt {attempt}: received {len(raw):,} characters from {client.model}"})
        try:
            parsed = parse_llm_json(raw)
        except LLMOutputError as exc:
            warnings.append(f"[{name}] attempt {attempt}: {exc}")
            trace.append({"tool": "validation_tool", "supplier": name, "detail": f"unparseable: {exc}"})
            retry_note = f"Your previous reply was rejected ({exc}). Reply with ONE valid JSON object only."
            continue
        card, w = normalize_scorecard(parsed, criteria, name, doc.text)
        warnings.extend(w)
        trace.append({"tool": "validation_tool", "supplier": name,
                      "detail": f"scorecard normalised with {len(w)} warning(s)"})
        return card.model_dump()

    reason = f"no valid JSON after {config.MAX_LLM_ATTEMPTS} attempts"
    warnings.append(f"[{name}] {reason}; supplier could not be scored.")
    return failed_scorecard(criteria, name, reason).model_dump()


def run_evaluation(inputs: list[SupplierInput], client: LLMClient,
                   progress: ProgressFn | None = None) -> dict[str, Any]:
    """Execute a full RFP run and return (and persist) the complete result document."""
    report = progress or (lambda frac, msg: None)
    errors = validate_inputs(inputs)
    if errors:
        raise EvaluationError("; ".join(errors))

    # Step: reload the LATEST active criteria so edits made in the DB / UI are always honoured.
    criteria = db.get_active_criteria()
    try:
        validate_criteria(criteria)
    except CriteriaError as exc:
        raise EvaluationError(str(exc)) from exc

    run_id = _new_run_id()
    db.create_run(run_id, client.provider, client.model, criteria)
    trace: list[dict[str, str]] = [{"tool": "orchestrator", "supplier": "",
                                    "detail": f"run {run_id} created with {len(criteria)} active criteria "
                                              f"and {len(inputs)} supplier(s)"}]
    warnings: list[str] = []
    try:
        entries = []
        for i, s in enumerate(inputs):
            report(i / (len(inputs) + 1), f"Evaluating {s.supplier_name.strip()} ({i + 1}/{len(inputs)})...")
            card = _evaluate_one(client, criteria, s, trace, warnings)
            entries.append({"supplier_name": s.supplier_name.strip(), "submission_date": s.submission_date,
                            "experience_rating": float(s.experience_rating), "scorecard": card,
                            "filename": s.filename})

        failed = [e for e in entries if e["scorecard"]["evaluation_status"] == "failed"]
        if len(failed) == len(entries):
            raise EvaluationError("No supplier could be evaluated. " + " | ".join(warnings[:3]))

        report(len(inputs) / (len(inputs) + 1), "Calculating benchmarks, PPI and ranking...")
        ranked = rank_suppliers(criteria, entries)
        trace.append({"tool": "ranking_tool", "supplier": "",
                      "detail": "benchmarks, gaps, relative %, PPI computed; ranks assigned with tie-break rules"})
        files = {e["supplier_name"]: e["filename"] for e in entries}
        for s in ranked["suppliers"]:
            s["source_file"] = files.get(s["supplier_name"], "")

        result = {
            "rfp_run_id": run_id,
            "created_at": db.now_iso(),
            "status": "COMPLETED_WITH_WARNINGS" if warnings else "COMPLETED",
            "provider": client.provider,
            "model": client.model,
            "criteria": criteria,
            "tie_break_rules": TIE_BREAK_RULES,
            "benchmarks": ranked["benchmarks"],
            "suppliers": ranked["suppliers"],
            "tie_break_explanations": ranked["tie_break_explanations"],
            "warnings": warnings,
            "agent_trace": trace,
        }
        db.save_run(result)
        trace.append({"tool": "orchestrator", "supplier": "", "detail": "results persisted to SQLite"})
        report(1.0, "Done.")
        return result
    except Exception as exc:
        db.mark_run_failed(run_id, str(exc))
        if isinstance(exc, EvaluationError):
            raise
        raise EvaluationError(f"Unexpected error during the run: {exc}") from exc

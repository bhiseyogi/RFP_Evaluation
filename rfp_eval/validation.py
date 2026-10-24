"""Validation Tool: turn raw LLM text into a clean, complete, in-range scorecard.

Rules (all recorded as warnings, never silent):
  * JSON is extracted from markdown fences / surrounding prose if necessary.
  * Results are matched to active criteria by criterion_id, falling back to criterion name.
  * Unknown criteria are ignored; duplicate results keep the first one.
  * A missing or non-numeric score becomes 0 and is flagged ``imputed``.
  * NaN / inf / booleans are treated as non-numeric.
  * If the model reports a different max_score, the score is rescaled to the database max_score.
  * Negative scores are clipped to 0 and scores above max are clipped to max.
  * Evidence is checked against the source document (informational flag, does not change scores).
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel, Field


class LLMOutputError(Exception):
    """The model output could not be parsed as a JSON object at all."""


class CriterionResult(BaseModel):
    criterion_id: int
    name: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    justification: str = ""
    evidence: str = ""
    evidence_verified: bool | None = None   # None = no evidence quoted
    status: str = "ok"                      # ok | clipped | rescaled | imputed


class Scorecard(BaseModel):
    supplier_name: str
    criteria: list[CriterionResult]
    risks: list[str] = []
    overall_summary: str = ""
    evaluation_status: str = "ok"           # ok | failed


# ----------------------------------------------------------------------------- parsing
def parse_llm_json(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from model output."""
    if not raw or not raw.strip():
        raise LLMOutputError("Empty response from the model.")
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMOutputError("No JSON object found in the model response.")
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMOutputError(f"Malformed JSON: {exc.msg} (line {exc.lineno}).") from exc
    if not isinstance(obj, dict):
        raise LLMOutputError("The JSON root must be an object.")
    return obj


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+(?:\.\d+)?)?\s*", value)
        if not m:
            return None
        num = float(m.group(1))
    else:
        return None
    return num if math.isfinite(num) else None


def _to_int(value: Any) -> int | None:
    num = _to_number(value)
    return int(num) if num is not None and float(num).is_integer() else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’]", "", s)).strip().lower()


def evidence_in_document(evidence: str, doc_text: str) -> bool:
    """True if every sizeable fragment of the quoted evidence occurs in the document."""
    doc = _norm(re.sub(r"\[Page \d+\]", " ", doc_text))
    fragments = [f for f in re.split(r"\.\.\.|…", _norm(evidence)) if len(f.strip()) >= 15]
    return bool(fragments) and all(f.strip() in doc for f in fragments)


# ----------------------------------------------------------------------------- normalisation
def normalize_scorecard(
    raw: dict[str, Any], criteria: list[dict[str, Any]], supplier_name: str, doc_text: str = ""
) -> tuple[Scorecard, list[str]]:
    warnings: list[str] = []
    tag = f"[{supplier_name}]"

    returned = raw.get("criteria")
    if not isinstance(returned, list):
        warnings.append(f"{tag} 'criteria' is missing or not a list; every criterion was set to 0.")
        returned = []

    by_id = {c["criterion_id"]: c for c in criteria}
    by_name = {c["name"].strip().lower(): c for c in criteria}
    matched: dict[int, dict[str, Any]] = {}

    for item in returned:
        if not isinstance(item, dict):
            warnings.append(f"{tag} ignored a criterion entry that is not an object.")
            continue
        cid = _to_int(item.get("criterion_id"))
        crit = by_id.get(cid) if cid is not None else None
        if crit is None and isinstance(item.get("name"), str):
            crit = by_name.get(item["name"].strip().lower())
        if crit is None:
            warnings.append(f"{tag} ignored a result for unknown criterion_id={item.get('criterion_id')!r}.")
            continue
        if crit["criterion_id"] in matched:
            warnings.append(f"{tag} duplicate result for '{crit['name']}'; kept the first one.")
            continue
        matched[crit["criterion_id"]] = item

    results: list[CriterionResult] = []
    for crit in criteria:
        db_max = float(crit["max_score"])
        item = matched.get(crit["criterion_id"])
        if item is None:
            warnings.append(f"{tag} no result returned for '{crit['name']}'; score set to 0.")
            results.append(CriterionResult(
                criterion_id=crit["criterion_id"], name=crit["name"], score=0, max_score=db_max,
                justification="No result was returned by the model for this criterion.", status="imputed"))
            continue

        status = "ok"
        score = _to_number(item.get("score"))
        if score is None:
            warnings.append(f"{tag} non-numeric score {item.get('score')!r} for '{crit['name']}'; set to 0.")
            score, status = 0.0, "imputed"
        else:
            llm_max = _to_number(item.get("max_score"))
            if llm_max and llm_max > 0 and abs(llm_max - db_max) > 1e-9:
                if 0 <= score <= llm_max:
                    new = score / llm_max * db_max
                    warnings.append(f"{tag} '{crit['name']}': model used max_score={llm_max:g}; "
                                    f"rescaled {score:g}/{llm_max:g} -> {new:g}/{db_max:g}.")
                    score, status = new, "rescaled"
            if score < 0:
                warnings.append(f"{tag} '{crit['name']}': negative score {score:g} clipped to 0.")
                score, status = 0.0, "clipped"
            elif score > db_max:
                warnings.append(f"{tag} '{crit['name']}': score {score:g} above max {db_max:g} clipped to max.")
                score, status = db_max, "clipped"

        justification = str(item.get("justification") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        verified: bool | None = None
        if evidence:
            verified = evidence_in_document(evidence, doc_text) if doc_text else None
            if verified is False:
                warnings.append(f"{tag} evidence for '{crit['name']}' was not found verbatim in the document.")
        elif score > 0 and status != "imputed":
            warnings.append(f"{tag} '{crit['name']}' scored {score:g} without supporting evidence.")
        results.append(CriterionResult(
            criterion_id=crit["criterion_id"], name=crit["name"], score=round(score, 4), max_score=db_max,
            justification=justification, evidence=evidence, evidence_verified=verified, status=status))

    risks = raw.get("risks")
    risks = [str(r).strip() for r in risks if str(r).strip()] if isinstance(risks, list) else []
    card = Scorecard(supplier_name=supplier_name, criteria=results, risks=risks,
                     overall_summary=str(raw.get("overall_summary") or "").strip())
    return card, warnings


def failed_scorecard(criteria: list[dict[str, Any]], supplier_name: str, reason: str) -> Scorecard:
    """All-zero scorecard used when a supplier could not be evaluated at all."""
    return Scorecard(
        supplier_name=supplier_name, evaluation_status="failed",
        criteria=[CriterionResult(criterion_id=c["criterion_id"], name=c["name"], score=0,
                                  max_score=float(c["max_score"]), status="imputed",
                                  justification=f"Not evaluated: {reason}") for c in criteria],
        risks=[f"Evaluation failed: {reason}"], overall_summary="Evaluation failed; scores are placeholders.")

"""Offline "mock LLM" so the whole app runs with no API key (demos, tests, CI).

IMPORTANT: this is a transparent keyword-indicator heuristic, NOT a language model. It exists to
exercise the pipeline end to end and to produce a reproducible sample export. Real evaluations
should use an actual LLM provider. Like a real LLM it returns JSON text, which then goes through
exactly the same validation as any other provider.

A second mode (``faulty=True``) deliberately corrupts the output (markdown fences, a missing
criterion, an out-of-range score, a non-numeric score, an unknown criterion id) so the
validation layer can be demonstrated.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .prompts import CRITERIA_MARK, DOC_END, DOC_START

NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen)"
# Phrases that postpone a deliverable ("will be provided after contract award", "on request" ...).
DEFERRAL = (r"after contract award|at (project )?kick-?off|after go-live|"
            r"(shared|provided|available|quoted|priced) (on request|separately)|on request|can be shared", -1.0)
TBC = (r"to be (finali[sz]ed|confirmed|defined|determined|quoted)|\btbd\b|will be (finali[sz]ed|defined)|"
       r"subject to scoping", -1.5)

# (regex, weight). Positive weights = concrete evidence; negative = vagueness / gaps.
# `target` is the weighted-hit total that earns the full max_score.
CUES: dict[str, dict[str, Any]] = {
    "technical": {
        "target": 15.0,
        "cues": [
            (r"architecture", 1.0),
            (r"micro-?services?|event-driven|api[- ]first", 1.0),
            (r"rest(ful)? apis?|graphql|webhooks?", 1.0),
            (r"kubernetes|auto-?scal|horizontal(ly)? scal", 1.5),
            (r"load[- ]test|throughput|transactions per|concurrent", 1.5),
            (r"sustained [\d,]+ transactions|median (processing )?latency|test report", 2.0),   # measured evidence
            (r"canonical|data model|field[- ]level mapping|schema", 1.0),
            (r"kafka|message queue|event bus|rabbitmq", 1.0),
            (r"high availability|multi-az|failover", 1.0),
            (r"99\.95", 0.5),
            (r"bapi|idoc", 1.0),
            (r"connectors?", 1.0),
            (r"integration (platform|layer)|adapters?|orchestration engine", 1.0),
            TBC,
            (r"generic|standard connectors? only|best practices?", -0.5),
        ],
    },
    "implementation": {
        "target": 12.0,
        "cues": [
            (r"phase \d|sprint", 1.0),
            (r"milestone", 1.0),
            (r"raci|steering committee|governance", 1.0),
            (r"project manager|delivery lead|scrum master|solution architect", 1.0),
            (rf"fte|full-time|team of {NUM}|{NUM} (engineers|consultants|specialists)", 1.0),
            (r"risk register|risk log|mitigation", 1.0),
            (r"risk register with owners|initial risks", 1.5),
            (r"uat|user acceptance", 1.0),
            (r"cut-?over|go-live", 1.0),
            (r"rollback|roll-back|contingency", 1.0),
            (r"rehears", 0.5),
            (r"hypercare", 0.5),
            (r"knowledge transfer|training", 0.5),
            DEFERRAL,
            TBC,
        ],
    },
    "commercial": {
        "target": 13.0,
        "cues": [
            (r"price (table|summary|breakdown)|pricing summary", 1.0),
            (r"total (cost|price|contract)", 1.5),
            (r"\binr\b|rs\.|crore|lakh", 1.0),
            (r"assumption", 1.0),
            (r"payment terms|payment milestones", 1.0),
            (r"fixed[- ]price|fixed fee|fixed all-inclusive", 1.0),
            (r"all-inclusive|inclusive of", 1.0),
            (r"change request|rate card", 0.5),
            (r"valid for \d+ days", 0.5),
            (r"lowest|competitive", 0.5),
            (r"optional|priced separately|quoted separately", -1.0),
            TBC,
        ],
    },
    "security": {
        "target": 15.0,
        "cues": [
            (r"iso/?\s?(iec )?27001", 1.5),
            (r"soc ?2", 1.5),
            (r"soc ?2 type ii report", 1.0),
            (r"penetration test|pen[- ]test|vapt", 1.0),
            (r"aes-?256|encryption at rest|encrypted (storage|in transit|at rest)|\btls", 1.0),
            (r"role-based|rbac|least privilege|multi-factor|mfa", 1.0),
            (r"\bsso\b", 0.5),
            (r"audit (log|trail)", 1.0),
            (r"immutable|siem", 1.0),
            (r"data residency|india region|hosted in", 1.0),
            (r"dpdp|gdpr", 0.5),
            (r"rto|rpo|disaster recovery", 1.0),
            (r"rto of [1-4] hours|tested twice", 1.0),
            (r"incident response|vulnerability management", 0.5),
            (r"certification (is )?in progress|will be obtained|aspire", -1.5),
            (r"planned for|industry best practices|best practices|industry standard", -1.0),
            DEFERRAL,
        ],
    },
    "support": {
        "target": 9.0,
        "cues": [
            (r"24\s?x\s?7|24/7", 1.5),
            (r"\bsla\b|service level", 1.0),
            (r"service credit", 1.0),
            (r"technical account manager|\btam\b|named (support|account)", 1.0),
            (r"p1|severity 1|priority 1|response time", 1.0),
            (r"resolution target", 0.5),
            (r"similar (projects?|engagements?|deployments?|integration)", 1.0),
            (r"references?:", 1.0),
            (rf"\b(?:{NUM}) similar|{NUM} similar integration|completed 1\d similar", 1.0),
            (r"customer satisfaction|csat|nps|retention", 0.5),
            (r"years of experience|since 20[01]\d|more than fifteen years", 0.5),
            (r"first (such )?(project|engagement)|limited experience|recently (founded|established)|one similar", -2.0),
            (r"email (support )?only|business hours|best[- ]effort", -1.0),
            (r"(on request|available on request)", -1.0),
        ],
    },
}


def _price_bonus(doc: str) -> float:
    """Lower stated total price -> more value points (budget ceiling INR 500 lakh, up to +12)."""
    m = re.search(r"total contract price\s*(?:\([^)]*\))?\s*(\d{2,4}(?:\.\d+)?)", doc, flags=re.IGNORECASE)
    if not m:
        return 0.0
    return max(0.0, 12.0 * (1 - float(m.group(1)) / 500.0))


def _group_for(name: str) -> str | None:
    n = name.lower()
    for key, pattern in [("technical", "technic|architect|integrat"), ("implementation", "implement|delivery|plan"),
                         ("commercial", "commercial|price|pricing|cost|value"),
                         ("security", "secur|complian|privacy"), ("support", "support|experience|reference")]:
        if re.search(pattern, n):
            return key
    return None


def _sentences(doc: str) -> list[str]:
    flat = re.sub(r"\[Page \d+\]", " ", doc)
    flat = re.sub(r"[ \t]*\n[ \t]*", " ", flat)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if len(s.strip()) > 20]


def _score_criterion(c: dict[str, Any], doc: str, sentences: list[str]) -> dict[str, Any]:
    group = _group_for(c["name"])
    if group:
        spec = CUES[group]
    else:  # unknown criterion -> use content words from its own name/description
        words = sorted({w for w in re.findall(r"[a-z]{5,}", f"{c['name']} {c['description']}".lower())})
        spec = {"target": max(3.0, len(words) * 0.5), "cues": [(re.escape(w), 1.0) for w in words]}

    total, matched, best = 0.0, [], (0.0, "")
    low = doc.lower()
    for pattern, weight in spec["cues"]:
        hit = re.search(pattern, low)
        if not hit:
            continue
        total += weight
        matched.append(hit.group(0).strip())
        sentence = next((s for s in sentences if re.search(pattern, s.lower())), "")
        if sentence and abs(weight) >= abs(best[0]) and (weight > 0 or best[0] <= 0):
            best = (weight, sentence)
    if group == "commercial":
        bonus = _price_bonus(doc)
        if bonus:
            total += bonus
            matched.append(f"competitive price (+{bonus:.1f})")
    frac = max(0.0, min(1.0, total / spec["target"]))
    score = round(frac * float(c["max_score"]) * 2) / 2  # half-point steps
    evidence = best[1][:240]
    shown = ", ".join(dict.fromkeys(matched[:6])) or "no relevant indicators"
    return {
        "criterion_id": c["criterion_id"],
        "score": score,
        "max_score": c["max_score"],
        "justification": f"[offline heuristic] Indicator coverage {frac:.0%}; matched: {shown}.",
        "evidence": evidence,
    }


def mock_scorecard(user_prompt: str) -> dict[str, Any]:
    supplier = user_prompt.splitlines()[0].replace("Supplier:", "").strip()
    crit_json = user_prompt.split(CRITERIA_MARK, 1)[1].split("Required JSON output format:", 1)[0]
    criteria = [
        {"criterion_id": c["criterion_id"], "name": c["name"], "description": c.get("what_to_inspect", ""),
         "max_score": c["max_score"]}
        for c in json.loads(crit_json)
    ]
    doc = user_prompt.split(DOC_START, 1)[1].split(DOC_END, 1)[0]
    sentences = _sentences(doc)
    results = [_score_criterion(c, doc, sentences) for c in criteria]
    risks = []
    for r, c in zip(results, criteria):
        if r["score"] <= 0.5 * float(c["max_score"]):
            risks.append(f"Weak or unclear evidence for '{c['name']}'.")
    return {
        "supplier_name": supplier,
        "criteria": results,
        "risks": risks or ["No major gaps identified by the offline heuristic."],
        "overall_summary": "Offline heuristic summary: scores reflect keyword-indicator coverage per criterion.",
    }


def mock_response(user_prompt: str, faulty: bool = False) -> str:
    card = mock_scorecard(user_prompt)
    if not faulty:
        return json.dumps(card, indent=2)
    crit = card["criteria"]
    if len(crit) >= 2:
        crit.pop(-1)                                   # a criterion is missing
        crit[0]["score"] = crit[0]["max_score"] + 4     # out of range  -> clipped
    if len(crit) >= 3:
        crit[1]["score"] = "seven out of ten"           # not numeric   -> imputed 0
    crit.append({"criterion_id": 999, "score": 5, "max_score": 10,   # unknown id -> ignored
                 "justification": "n/a", "evidence": ""})
    return "Sure! Here is the evaluation:\n```json\n" + json.dumps(card, indent=2) + "\n```"

"""SQLite persistence: criteria, runs and per-supplier results."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_criteria (
    criterion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL DEFAULT '',
    weight       REAL NOT NULL CHECK (weight >= 0),
    max_score    REAL NOT NULL DEFAULT 10 CHECK (max_score > 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS rfp_runs (
    rfp_run_id        TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL,            -- RUNNING | COMPLETED | COMPLETED_WITH_WARNINGS | FAILED
    provider          TEXT,
    model             TEXT,
    criteria_snapshot TEXT,                     -- JSON: the exact criteria used for this run
    warnings_json     TEXT,
    tie_break_json    TEXT
);

CREATE TABLE IF NOT EXISTS supplier_results (
    rfp_run_id        TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
    supplier_name     TEXT NOT NULL,
    submission_date   TEXT NOT NULL,
    experience_rating REAL NOT NULL,
    absolute_score    REAL NOT NULL,
    ppi               REAL NOT NULL,
    final_rank        INTEGER NOT NULL,
    result_json       TEXT NOT NULL,
    PRIMARY KEY (rfp_run_id, supplier_name)
);
"""

SEED_CRITERIA = [
    ("Technical Capability",
     "Architecture, integrations, scalability, technical fit with the stated requirement.", 30, 10),
    ("Implementation Plan",
     "Timeline, milestones, staffing, delivery governance and risk plan.", 20, 10),
    ("Commercial Value",
     "Pricing clarity, total cost of ownership, assumptions and value for money.", 20, 10),
    ("Security & Compliance",
     "Security controls, certifications, privacy, data residency and auditability.", 20, 10),
    ("Support & Experience",
     "Support model and SLAs, similar past projects, named references.", 10, 10),
]


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    """Create tables and (if the criteria table is empty) insert the sample criteria."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        if seed and conn.execute("SELECT COUNT(*) FROM evaluation_criteria").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO evaluation_criteria (name, description, weight, max_score, is_active) "
                "VALUES (?, ?, ?, ?, 1)",
                SEED_CRITERIA,
            )


# ----------------------------------------------------------------------------- criteria
def _criteria(where: str = "") -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM evaluation_criteria {where} ORDER BY criterion_id"
        ).fetchall()
    return [{**dict(r), "is_active": bool(r["is_active"])} for r in rows]


def get_all_criteria() -> list[dict[str, Any]]:
    return _criteria()


def get_active_criteria() -> list[dict[str, Any]]:
    return _criteria("WHERE is_active = 1")


def update_criteria(rows: list[dict[str, Any]]) -> None:
    with connect() as conn:
        for r in rows:
            conn.execute(
                "UPDATE evaluation_criteria SET description=?, weight=?, max_score=?, is_active=? "
                "WHERE criterion_id=?",
                (r["description"], float(r["weight"]), float(r["max_score"]),
                 int(bool(r["is_active"])), int(r["criterion_id"])),
            )


def add_criterion(name: str, description: str, weight: float, max_score: float, is_active: bool) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO evaluation_criteria (name, description, weight, max_score, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            (name.strip(), description.strip(), float(weight), float(max_score), int(is_active)),
        )


# ----------------------------------------------------------------------------- runs
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_run(run_id: str, provider: str, model: str, criteria: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO rfp_runs (rfp_run_id, created_at, status, provider, model, criteria_snapshot) "
            "VALUES (?, ?, 'RUNNING', ?, ?, ?)",
            (run_id, now_iso(), provider, model, json.dumps(criteria)),
        )


def save_run(result: dict[str, Any]) -> None:
    """Persist the complete outcome atomically (one transaction, one RFP_RUN_ID)."""
    run_id = result["rfp_run_id"]
    with connect() as conn:
        conn.execute("DELETE FROM supplier_results WHERE rfp_run_id = ?", (run_id,))
        for s in result["suppliers"]:
            conn.execute(
                "INSERT INTO supplier_results (rfp_run_id, supplier_name, submission_date, "
                "experience_rating, absolute_score, ppi, final_rank, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, s["supplier_name"], s["submission_date"], s["experience_rating"],
                 s["absolute_score"], s["ppi"], s["final_rank"], json.dumps(s)),
            )
        conn.execute(
            "UPDATE rfp_runs SET status=?, warnings_json=?, tie_break_json=? WHERE rfp_run_id=?",
            (result["status"], json.dumps(result["warnings"]),
             json.dumps(result["tie_break_explanations"]), run_id),
        )


def mark_run_failed(run_id: str, message: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE rfp_runs SET status='FAILED', warnings_json=? WHERE rfp_run_id=?",
                     (json.dumps([message]), run_id))


def list_runs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT r.rfp_run_id, r.created_at, r.status, r.provider, r.model, "
            "       COUNT(s.supplier_name) AS suppliers "
            "FROM rfp_runs r LEFT JOIN supplier_results s USING (rfp_run_id) "
            "GROUP BY r.rfp_run_id ORDER BY r.created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def load_run(run_id: str) -> dict[str, Any] | None:
    """Rebuild the full result document for a stored run."""
    with connect() as conn:
        run = conn.execute("SELECT * FROM rfp_runs WHERE rfp_run_id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        sup = conn.execute(
            "SELECT result_json FROM supplier_results WHERE rfp_run_id = ? ORDER BY final_rank",
            (run_id,),
        ).fetchall()
    suppliers = [json.loads(r["result_json"]) for r in sup]
    criteria = json.loads(run["criteria_snapshot"] or "[]")
    benchmarks: dict[str, float] = {}
    for c in criteria:
        scores = [cr["score"] for s in suppliers for cr in s["criteria"]
                  if cr["criterion_id"] == c["criterion_id"]]
        benchmarks[str(c["criterion_id"])] = max(scores) if scores else 0
    return {
        "rfp_run_id": run["rfp_run_id"],
        "created_at": run["created_at"],
        "status": run["status"],
        "provider": run["provider"],
        "model": run["model"],
        "criteria": criteria,
        "benchmarks": benchmarks,
        "suppliers": suppliers,
        "warnings": json.loads(run["warnings_json"] or "[]"),
        "tie_break_explanations": json.loads(run["tie_break_json"] or "[]"),
        "agent_trace": [],
    }

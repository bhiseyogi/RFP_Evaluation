"""Run the full pipeline on the four sample PDFs and write sample_output/sample_run.json.

Uses the offline mock provider so it is reproducible without an API key. To export a run from a real
LLM, use the Download button in the app instead.

    python scripts/make_sample_export.py [--faulty]
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["RFP_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "export.db")   # never touch the real DB

from rfp_eval import db  # noqa: E402
from rfp_eval.llm import MockClient  # noqa: E402
from rfp_eval.orchestrator import SupplierInput, run_evaluation  # noqa: E402

SUPPLIERS = [  # file stem, display name, submission date, experience rating
    ("Apex_Systems", "Apex Systems", date(2026, 10, 5), 8.5),
    ("BrightPath_Tech", "BrightPath Tech", date(2026, 10, 7), 5.0),
    ("NexaWorks", "NexaWorks", date(2026, 10, 6), 8.0),
    ("Orbit_Digital", "Orbit Digital", date(2026, 10, 4), 9.0),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faulty", action="store_true", help="use the malformed-output mock (validation demo)")
    args = parser.parse_args()
    db.init_db()
    inputs = []
    for stem, name, d, rating in SUPPLIERS:
        pdf = ROOT / "sample_rfps" / f"{stem}_RFP_Response.pdf"
        inputs.append(SupplierInput(name, d, rating, pdf.name, pdf.read_bytes()))
    result = run_evaluation(inputs, MockClient(faulty=args.faulty))
    out = ROOT / "sample_output" / ("sample_run_with_validation_warnings.json" if args.faulty else "sample_run.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"{result['rfp_run_id']} -> {out} ({result['status']}, {len(result['warnings'])} warnings)")
    for s in result["suppliers"]:
        print(f"  #{s['final_rank']} {s['supplier_name']:<16} abs={s['absolute_score']:.2f} PPI={s['ppi']:.2f}")


if __name__ == "__main__":
    main()

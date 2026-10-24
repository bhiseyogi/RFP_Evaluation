import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rfp_eval import config, db  # noqa: E402
from rfp_eval.orchestrator import SupplierInput  # noqa: E402

SAMPLES = [("Apex_Systems", "Apex Systems", date(2026, 10, 5), 8.5),
           ("BrightPath_Tech", "BrightPath Tech", date(2026, 10, 7), 5.0),
           ("NexaWorks", "NexaWorks", date(2026, 10, 6), 8.0),
           ("Orbit_Digital", "Orbit Digital", date(2026, 10, 4), 9.0)]


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Every test gets its own empty, freshly seeded database."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return config.DB_PATH


@pytest.fixture
def sample_inputs():
    return [SupplierInput(name, d, r, f"{stem}.pdf",
                          (ROOT / "sample_rfps" / f"{stem}_RFP_Response.pdf").read_bytes())
            for stem, name, d, r in SAMPLES]

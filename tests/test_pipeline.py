import json

import pytest

from rfp_eval import config, db, prompts
from rfp_eval.llm import MockClient
from rfp_eval.orchestrator import EvaluationError, SupplierInput, run_evaluation, validate_inputs
from rfp_eval.pdf_tool import PDFExtractionError, extract_text


def test_sample_pdfs_are_2_to_4_pages_and_extractable(sample_inputs):
    for s in sample_inputs:
        doc = extract_text(s.pdf_bytes)
        assert 2 <= doc.pages <= 4 and doc.chars > 1500


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4 garbage"])
def test_bad_pdfs_are_rejected(data):
    with pytest.raises(PDFExtractionError):
        extract_text(data)


def test_scanned_style_pdf_without_text_is_rejected():
    from io import BytesIO
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    with pytest.raises(PDFExtractionError, match="almost no extractable text"):
        extract_text(buf.getvalue())


def test_end_to_end_run_persists_everything(sample_inputs):
    res = run_evaluation(sample_inputs, MockClient())
    assert [s["final_rank"] for s in res["suppliers"]] == [1, 2, 3, 4]
    assert res["rfp_run_id"].startswith("RFP-")
    json.dumps(res)                                           # fully serialisable
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM rfp_runs WHERE rfp_run_id=?", (res["rfp_run_id"],)).fetchone()[0] \
            == res["status"]
        rows = conn.execute("SELECT supplier_name, final_rank, ppi, absolute_score, result_json FROM supplier_results "
                            "WHERE rfp_run_id=? ORDER BY final_rank", (res["rfp_run_id"],)).fetchall()
    assert [r["supplier_name"] for r in rows] == [s["supplier_name"] for s in res["suppliers"]]
    assert json.loads(rows[0]["result_json"])["criteria"][0]["name"]
    loaded = db.load_run(res["rfp_run_id"])
    assert [s["supplier_name"] for s in loaded["suppliers"]] == [s["supplier_name"] for s in res["suppliers"]]
    assert loaded["benchmarks"] == res["benchmarks"]


def test_same_inputs_same_ordering_and_numbers(sample_inputs):
    a = run_evaluation(sample_inputs, MockClient())
    b = run_evaluation(list(reversed(sample_inputs)), MockClient())
    strip = lambda r: [(s["supplier_name"], s["final_rank"], s["absolute_score"], s["ppi"]) for s in r["suppliers"]]
    assert strip(a) == strip(b)


def test_sample_profiles_match_the_brief(sample_inputs):
    res = {s["supplier_name"]: {c["name"]: c["score"] for c in s["criteria"]}
           for s in run_evaluation(sample_inputs, MockClient())["suppliers"]}
    assert res["Apex Systems"]["Technical Capability"] == max(r["Technical Capability"] for r in res.values())
    assert res["Apex Systems"]["Security & Compliance"] == max(r["Security & Compliance"] for r in res.values())
    assert res["NexaWorks"]["Implementation Plan"] == max(r["Implementation Plan"] for r in res.values())
    assert res["BrightPath Tech"]["Commercial Value"] == max(r["Commercial Value"] for r in res.values())
    assert res["BrightPath Tech"]["Security & Compliance"] <= 2


def test_faulty_llm_output_is_repaired_with_warnings(sample_inputs):
    res = run_evaluation(sample_inputs, MockClient(faulty=True))
    assert res["status"] == "COMPLETED_WITH_WARNINGS" and len(res["suppliers"]) == 4
    text = " ".join(res["warnings"])
    for expected in ("above max", "non-numeric", "no result returned", "unknown criterion_id"):
        assert expected in text
    for s in res["suppliers"]:
        assert all(0 <= c["score"] <= c["max_score"] for c in s["criteria"])
        assert len(s["criteria"]) == 5


def test_criteria_are_reloaded_from_db_each_run(sample_inputs):
    seen = []

    class Spy(MockClient):
        def complete(self, system, user):
            seen.append(user)
            return super().complete(system, user)

    db.update_criteria([{**c, "is_active": c["name"] != "Support & Experience",
                         "weight": {"Technical Capability": 35, "Implementation Plan": 25}.get(c["name"], c["weight"])}
                        for c in db.get_all_criteria()])
    res = run_evaluation(sample_inputs, Spy())
    assert len(res["criteria"]) == 4 and sum(c["weight"] for c in res["criteria"]) == 100
    assert all("Support & Experience" not in u.split(prompts.DOC_START)[0] for u in seen)
    assert all(len(s["criteria"]) == 4 for s in res["suppliers"])


def test_weights_not_exposed_to_the_llm():
    crit = db.get_active_criteria()
    assert all("weight" not in c for c in prompts.criteria_for_prompt(crit))


def test_bad_weights_block_the_run(sample_inputs):
    db.update_criteria([{**c, "weight": 10} for c in db.get_all_criteria()])
    with pytest.raises(EvaluationError, match="must total"):
        run_evaluation(sample_inputs, MockClient())
    assert db.list_runs() == []


def test_one_unreadable_pdf_does_not_sink_the_run(sample_inputs):
    sample_inputs[0] = SupplierInput("Broken Co", sample_inputs[0].submission_date, 5, "broken.pdf", b"%PDF-1.4 junk")
    res = run_evaluation(sample_inputs, MockClient())
    broken = next(s for s in res["suppliers"] if s["supplier_name"] == "Broken Co")
    assert broken["evaluation_status"] == "failed" and broken["absolute_score"] == 0
    assert any("[Broken Co]" in w for w in res["warnings"])


def test_all_failed_raises_and_marks_run_failed(sample_inputs):
    bad = [SupplierInput(f"S{i}", s.submission_date, 5, "x.pdf", b"nope") for i, s in enumerate(sample_inputs)]
    with pytest.raises(EvaluationError):
        run_evaluation(bad, MockClient())
    assert db.list_runs()[0]["status"] == "FAILED"


def test_unparseable_llm_reply_is_retried_then_failed(sample_inputs):
    class Garbage(MockClient):
        calls = 0

        def complete(self, system, user):
            Garbage.calls += 1
            return "I cannot help with that."

    with pytest.raises(EvaluationError):
        run_evaluation(sample_inputs, Garbage())
    assert Garbage.calls == len(sample_inputs) * config.MAX_LLM_ATTEMPTS


def test_input_validation(sample_inputs):
    a, b = sample_inputs[:2]
    assert validate_inputs([a]) and any("at least two" in e for e in validate_inputs([a]))
    dup = SupplierInput(a.supplier_name.upper(), a.submission_date, 5, "dup.pdf", b.pdf_bytes)
    assert any("duplicates" in e for e in validate_inputs([a, dup]))
    blank = SupplierInput("  ", a.submission_date, 5, "blank.pdf", b.pdf_bytes)
    assert any("name is required" in e for e in validate_inputs([a, blank]))
    bad_rating = SupplierInput("Z", a.submission_date, 11, "z.pdf", b.pdf_bytes)
    assert any("experience rating" in e for e in validate_inputs([a, bad_rating]))
    no_date = SupplierInput("Y", None, 5, "y.pdf", b.pdf_bytes)
    assert any("submission date" in e for e in validate_inputs([a, no_date]))
    assert validate_inputs([a, b]) == []

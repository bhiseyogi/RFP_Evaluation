import math

import pytest

from rfp_eval.validation import LLMOutputError, evidence_in_document, normalize_scorecard, parse_llm_json

CRITERIA = [
    {"criterion_id": 1, "name": "Technical Capability", "weight": 60, "max_score": 10},
    {"criterion_id": 2, "name": "Commercial Value", "weight": 40, "max_score": 10},
]
DOC = "The platform runs on Kubernetes with auto-scaling across three zones."


def card(*items, **extra):
    return {"criteria": list(items), **extra}


GOOD_EVIDENCE = "runs on Kubernetes with auto-scaling"     # a verbatim fragment of DOC


def item(cid, score, **kw):
    return {"criterion_id": cid, "score": score, "max_score": 10, "justification": "j",
            "evidence": GOOD_EVIDENCE, **kw}


def run(raw):
    return normalize_scorecard(raw, CRITERIA, "Acme", DOC)


def scores(sc):
    return [c.score for c in sc.criteria]


def test_parse_plain_fenced_and_prose():
    assert parse_llm_json('{"a": 1}') == {"a": 1}
    assert parse_llm_json('Sure!\n```json\n{"a": 1}\n```\nDone') == {"a": 1}
    assert parse_llm_json('Here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}


@pytest.mark.parametrize("bad", ["", "   ", "no json here", '{"a": ', "[1, 2]"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(LLMOutputError):
        parse_llm_json(bad)


def test_clean_input_has_no_warnings():
    sc, w = run(card(item(1, 8), item(2, 5)))
    assert scores(sc) == [8, 5] and w == []


def test_missing_criterion_is_imputed():
    sc, w = run(card(item(1, 8)))
    assert scores(sc) == [8, 0] and sc.criteria[1].status == "imputed"
    assert any("no result returned" in x for x in w)


def test_out_of_range_is_clipped():
    sc, w = run(card(item(1, 14), item(2, -3)))
    assert scores(sc) == [10, 0]
    assert [c.status for c in sc.criteria] == ["clipped", "clipped"] and len(w) == 2


@pytest.mark.parametrize("bad", ["seven", None, True, math.nan, math.inf, [], {}])
def test_non_numeric_scores_become_zero(bad):
    sc, w = run(card(item(1, bad), item(2, 5)))
    assert sc.criteria[0].score == 0 and sc.criteria[0].status == "imputed" and w


def test_numeric_strings_accepted():
    sc, _ = run(card(item(1, "8"), item(2, "7/10")))
    assert scores(sc) == [8, 7]


def test_different_max_score_is_rescaled():
    sc, w = run(card({"criterion_id": 1, "score": 80, "max_score": 100}, item(2, 5)))
    assert sc.criteria[0].score == 8 and sc.criteria[0].status == "rescaled" and w


def test_duplicates_and_unknown_ids():
    sc, w = run(card(item(1, 8), item(1, 2), item(2, 5), item(99, 9)))
    assert scores(sc) == [8, 5]
    assert any("duplicate" in x for x in w) and any("unknown" in x for x in w)


def test_match_by_name_when_id_missing():
    sc, _ = run(card({"name": "commercial value", "score": 6}, item(1, 7)))
    assert scores(sc) == [7, 6]


def test_criteria_not_a_list():
    sc, w = run({"criteria": "oops"})
    assert scores(sc) == [0, 0] and w


def test_always_returns_every_active_criterion_in_order():
    sc, _ = run(card(item(2, 5)))
    assert [c.criterion_id for c in sc.criteria] == [1, 2]


def test_evidence_verification():
    good = "runs on Kubernetes with auto-scaling"
    bad = "Our platform is certified to every standard known to mankind"
    assert evidence_in_document(good, DOC)
    assert evidence_in_document("runs on Kubernetes ... across three zones", DOC)
    assert not evidence_in_document(bad, DOC)
    sc, w = run(card(item(1, 8, evidence=bad), item(2, 5, evidence=good)))
    assert sc.criteria[0].evidence_verified is False and sc.criteria[1].evidence_verified is True
    assert any("not found verbatim" in x for x in w)
    assert scores(sc) == [8, 5]          # unverified evidence is flagged, never silently re-scored


def test_score_without_evidence_warns():
    _, w = run(card(item(1, 8, evidence=""), item(2, 0, evidence="")))
    assert len(w) == 1 and "without supporting evidence" in w[0]

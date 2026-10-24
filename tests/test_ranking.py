import random
from datetime import date

import pytest

from rfp_eval.ranking import CriteriaError, _sort_key, rank_suppliers, validate_criteria

CRITERIA = [
    {"criterion_id": 1, "name": "A", "weight": 60, "max_score": 10},
    {"criterion_id": 2, "name": "B", "weight": 40, "max_score": 10},
]


def supplier(name, scores, d=date(2026, 1, 1), exp=5.0):
    card = {"criteria": [{"criterion_id": i + 1, "score": s, "status": "ok"} for i, s in enumerate(scores)]}
    return {"supplier_name": name, "submission_date": d, "experience_rating": exp, "scorecard": card}


def test_hand_calculated_example():
    out = rank_suppliers(CRITERIA, [supplier("X", [8, 5]), supplier("Y", [6, 10])])
    assert out["benchmarks"] == {"1": 8, "2": 10}
    y, x = out["suppliers"]
    assert (y["supplier_name"], y["final_rank"]) == ("Y", 1)
    assert x["absolute_score"] == pytest.approx(0.8 * 60 + 0.5 * 40)       # 68
    assert y["absolute_score"] == pytest.approx(0.6 * 60 + 1.0 * 40)       # 76
    assert x["ppi"] == pytest.approx(100 * 0.6 + 50 * 0.4)                 # 80
    assert y["ppi"] == pytest.approx(75 * 0.6 + 100 * 0.4)                 # 85
    assert [c["gap"] for c in x["criteria"]] == [0, -5]
    assert [c["gap"] for c in y["criteria"]] == [-2, 0]
    assert [round(c["relative_pct"], 1) for c in y["criteria"]] == [75.0, 100.0]


def test_zero_benchmark_is_safe():
    out = rank_suppliers(CRITERIA, [supplier("X", [8, 0]), supplier("Y", [6, 0])])
    for s in out["suppliers"]:
        assert s["criteria"][1]["relative_pct"] == 100.0      # nobody beats anybody: all tied at the benchmark
        assert s["criteria"][1]["gap"] == 0


def test_tie_break_order():
    same = [5, 5]
    out = rank_suppliers(CRITERIA, [
        supplier("Delta", same, date(2026, 2, 1), 7),     # latest date
        supplier("Charlie", same, date(2026, 1, 1), 6),   # earliest date, lower experience
        supplier("Bravo", same, date(2026, 1, 1), 8),     # earliest date, higher experience
        supplier("Alpha", same, date(2026, 1, 1), 8),     # identical to Bravo -> name decides
    ])
    assert [s["supplier_name"] for s in out["suppliers"]] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert [s["final_rank"] for s in out["suppliers"]] == [1, 2, 3, 4]
    text = " ".join(out["tie_break_explanations"])
    assert "rule 2" in text and "rule 3" in text and "rule 4" in text


def test_ppi_beats_date():
    out = rank_suppliers(CRITERIA, [supplier("Early", [4, 4], date(2020, 1, 1), 10), supplier("Late", [9, 9])])
    assert out["suppliers"][0]["supplier_name"] == "Late"
    assert "rule 1" in out["tie_break_explanations"][0]


def test_float_noise_cannot_change_order():
    a = {"supplier_name": "B", "ppi": 80.0, "submission_date": date(2026, 1, 1), "experience_rating": 5}
    b = {"supplier_name": "A", "ppi": 80.0 + 1e-12, "submission_date": date(2026, 1, 2), "experience_rating": 5}
    assert sorted([a, b], key=_sort_key)[0]["supplier_name"] == "B"     # tie on PPI -> earlier date wins


def test_input_order_does_not_matter():
    base = [supplier("S1", [7, 3]), supplier("S2", [5, 9], date(2026, 3, 1)), supplier("S3", [7, 3], date(2026, 1, 5)),
            supplier("S4", [2, 2])]
    expected = [s["supplier_name"] for s in rank_suppliers(CRITERIA, base)["suppliers"]]
    for seed in range(10):
        shuffled = base[:]
        random.Random(seed).shuffle(shuffled)
        assert [s["supplier_name"] for s in rank_suppliers(CRITERIA, shuffled)["suppliers"]] == expected


def test_imputed_scores_are_not_benchmarks():
    sup = [supplier("X", [5, 5]), supplier("Y", [5, 5])]
    sup[1]["scorecard"]["criteria"][0]["status"] = "imputed"
    assert rank_suppliers(CRITERIA, sup)["benchmarks"]["1"] == 5


@pytest.mark.parametrize("weights", [[60, 30], [], [70, 40]])
def test_weights_must_total_100(weights):
    crit = [{"criterion_id": i, "name": str(i), "weight": w, "max_score": 10} for i, w in enumerate(weights)]
    with pytest.raises(CriteriaError):
        validate_criteria(crit)

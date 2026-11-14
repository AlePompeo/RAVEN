# SPDX-License-Identifier: Apache-2.0
from backend.domain.raven import verdict as vd

A = {
    "useful_hours": 120.0,
    "unknown_hours": 0.0,
    "margin_min_db": 4.0,
    "min_soc": 0.6,
    "sun_hours": 200.0,
}
B = {
    "useful_hours": 96.0,
    "unknown_hours": 0.0,
    "margin_min_db": 9.0,
    "min_soc": 0.55,
    "sun_hours": 180.0,
}


def test_the_balanced_order_decides_on_useful_hours_and_lists_every_row() -> None:
    v = vd.decide(A, B)
    assert v["winner"] == "A" and v["decided_by"] == "useful_hours" and len(v["rows"]) == 5
    assert {r["component"]: r["better"] for r in v["rows"]}[
        "margin_min_db"
    ] == "B"  # B is better on margin: shown, it did not decide


def test_the_priority_changes_the_order_and_the_winner() -> None:
    assert (
        vd.decide(A, B, "radio")["winner"] == "B"
        and vd.decide(A, B, "radio")["decided_by"] == "margin_min_db"
    )
    assert (
        vd.decide(A, B, "sun")["winner"] == "A"
        and vd.decide(A, B, "unknown-priority")["order"][0] == "useful_hours"
    )


def test_a_difference_within_the_tolerance_is_a_tie_and_the_next_component_decides() -> None:
    close = {**B, "useful_hours": 120.5}
    v = vd.decide(A, close)
    assert v["decided_by"] == "margin_min_db" and v["winner"] == "B"
    assert vd.decide(A, A)["winner"] == "tie"


def test_unknown_components_never_decide_and_all_unknown_is_undetermined() -> None:
    v = vd.decide({**A, "useful_hours": None}, B)
    assert v["decided_by"] == "unknown_hours" or v["decided_by"] == "margin_min_db"
    assert {r["component"]: r["better"] for r in v["rows"]}["useful_hours"] == "unknown"
    none = {k: None for k in A}
    assert (
        vd.decide(none, B)["winner"] == "undetermined"
        and vd.decide(none, none)["winner"] == "undetermined"
    )
    assert (
        vd.decide({"useful_hours": float("nan")}, {"useful_hours": 5.0})["rows"][0]["better"]
        == "unknown"
    )


def test_smaller_unknown_hours_win() -> None:
    v = vd.decide(
        {**A, "useful_hours": 100.0, "unknown_hours": 5.0},
        {**B, "useful_hours": 100.0, "unknown_hours": 30.0},
    )
    assert v["decided_by"] == "unknown_hours" and v["winner"] == "A"


def test_the_template_text_uses_only_the_rows_and_says_what_is_unknown() -> None:
    v = vd.decide({**A, "min_soc": None}, B)
    txt = vd.template_text(v, ["Malapert Massif", "Haworth"])
    assert (
        "Malapert Massif (A)" in txt
        and "A 120 h, B 96.0 h" in txt
        and "minimum RF margin" in txt
        and "minimum state of charge" in txt
    )
    assert "undetermined" not in txt
    assert "cannot decide" in vd.template_text(vd.decide({k: None for k in A}, B), ["x", "y"])
    assert "tied" in vd.template_text(vd.decide(A, A), ["x", "y"])


def test_a_model_text_is_accepted_only_if_it_names_the_winner_and_uses_supplied_numbers() -> None:
    v = vd.decide(A, B)
    names = ["Malapert Massif", "Haworth"]
    good = "Malapert Massif is the better choice: it has 120 useful hours against 96, while Haworth keeps a larger RF margin (9.0 dB against 4.0)."
    assert vd.check_text(good, v, names)
    assert not vd.check_text(good.replace("120", "130"), v, names)  # an invented number
    assert not vd.check_text(
        "Haworth is the clear winner with 96 useful hours against 120 for the other site, no doubt.",
        v,
        names,
    )  # names the loser
    assert not vd.check_text("ok", v, names) and not vd.check_text("x" * 1000, v, names)

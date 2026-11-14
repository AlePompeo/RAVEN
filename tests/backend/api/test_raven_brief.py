# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.api.raven_brief import MissionBrief, parse_rules


def test_italian_prompt_fills_what_it_states_and_nothing_else() -> None:
    p = parse_rules(
        "Lander da 300 kg, 14 giorni da aprile 2027, almeno il 60% di sole, radio a 100 kbit/s, vicino al polo sud, dammi 5 siti"
    )
    b = p.brief
    assert b.mass_kg == 300 and b.days == 14 and b.start_utc == "2027-04-01T00:00:00Z"
    assert b.min_sun_percent == 60 and b.rate_bps == 100_000 and b.k == 5 and b.lat_max_deg == -75.0
    assert (
        b.mission_class is None
    )  # a mass is not mapped to a class (class masses are launch masses)
    assert b.priority is None and b.min_rf_percent is None and "priority" in p.unresolved


def test_english_prompt() -> None:
    p = parse_rules(
        "Find 3 sites for two weeks starting 2027-06-10 with at least 70% sunlight and 90% of communication, prioritize earth"
    )
    b = p.brief
    assert (b.k, b.days, b.start_utc, b.min_sun_percent, b.min_rf_percent, b.priority) == (
        3,
        14.0,
        "2027-06-10T00:00:00Z",
        70,
        90,
        "earth",
    )
    assert p.unresolved == []


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("rover, 10 giorni", "mission_class", "rover"),
        ("small lander for 5 days", "mission_class", "small_lander"),
        ("1,5 Mbps downlink", "rate_bps", 1_500_000),
        ("priorità al sole", "priority", "sun"),
        ("missione bilanciata", "priority", "balanced"),
        ("latitudine sotto -80", "lat_max_deg", -80),
        ("pendenza massima 8 gradi", "max_slope_deg", 8),
        ("siti distanti almeno 20 km", "min_distance_km", 20),
        ("un mese da maggio 2027", "days", 30),
    ],
)
def test_single_fields(text: str, field: str, value: object) -> None:
    assert getattr(parse_rules(text).brief, field) == value


def test_unsupported_requests_are_listed_not_turned_into_variables() -> None:
    p = parse_rules("trova 4 siti vicino al ghiaccio e all'acqua")
    assert p.unsupported == ["acqua", "ghiaccio"] and p.brief.k == 4
    assert not any(hasattr(p.brief, w) for w in ("water", "ice", "acqua"))


def test_out_of_range_values_are_rejected_not_clipped() -> None:
    p = parse_rules("almeno il 150% di sole, 500 giorni, 1 kbps")
    assert p.brief.min_sun_percent is None and p.brief.days is None and p.brief.rate_bps is None
    assert set(p.rejected) == {"min_sun_percent", "days", "rate_bps"}


def test_empty_and_odd_text_give_an_empty_brief_never_an_error() -> None:
    odd = chr(0) + chr(0x202E) + "%%% 99999999999999999999 giorni"
    for text in ("", "   ", "ciao come stai", "x" * 5000, odd):
        p = parse_rules(text)
        assert isinstance(p.brief, MissionBrief) and p.brief.k is None


def test_k_is_capped_and_zero_is_ignored() -> None:
    assert parse_rules("dammi 50 siti").brief.k == 10
    assert parse_rules("dammi 0 siti").brief.k is None


def test_the_api_parses_and_rejects_oversized_or_extra_fields() -> None:
    from fastapi.testclient import TestClient

    from backend.bootstrap import build_app

    c = TestClient(build_app())
    r = c.post("/api/raven/brief/parse", json={"text": "dammi 5 siti, 14 giorni da aprile 2027"})
    assert r.status_code == 200
    j = r.json()
    assert j["level"] == "rules" and j["brief"]["k"] == 5 and j["brief"]["days"] == 14
    assert "priority" in j["unresolved"]
    assert c.post("/api/raven/brief/parse", json={"text": "x" * 2001}).status_code == 422
    assert c.post("/api/raven/brief/parse", json={"text": "ok", "extra": 1}).status_code == 422

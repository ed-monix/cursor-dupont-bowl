"""Tests for post-gate apply helpers. No network."""

import json
from pathlib import Path

from lib.apply_gate import (
    collect_waiver_claims,
    expected_decision_name,
    standings_worst_to_best,
)


def test_standings_worst_to_best_record_then_points():
    order = standings_worst_to_best({
        "teams": {
            "a": {"wins": 2, "losses": 0, "ties": 0, "points_for": 100},
            "b": {"wins": 0, "losses": 2, "ties": 0, "points_for": 80},
            "c": {"wins": 2, "losses": 0, "ties": 0, "points_for": 90},
        }
    })
    assert order == ["b", "c", "a"]


def test_collect_waiver_claims_skips_lineup_and_trade(tmp_path: Path):
    d = tmp_path / "decisions"
    d.mkdir()
    (d / "kardashian.json").write_text(json.dumps({
        "claims": [{"add": "p1", "drop": None, "bid": 7}],
        "drops": [],
        "note_reply": "",
    }))
    (d / "kardashian.lineup-early.json").write_text(json.dumps({
        "starters": {}, "justification": "nope",
    }))
    (d / "kardashian.trade.json").write_text(json.dumps({"accept": False}))
    (d / "broken.json").write_text("{")
    claims = collect_waiver_claims(d)
    assert list(claims) == ["kardashian"]
    assert claims["kardashian"][0]["bid"] == 7


def test_expected_decision_names():
    assert expected_decision_name("costanza", "waivers", None) == "costanza.json"
    assert expected_decision_name("costanza", "lineups-early", None) == (
        "costanza.lineup-early.json"
    )
    assert expected_decision_name("costanza", "lineups-main", "main") == (
        "costanza.lineup-main.json"
    )

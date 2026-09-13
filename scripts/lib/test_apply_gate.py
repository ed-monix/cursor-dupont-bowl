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


def _ops(root: Path, **fields) -> None:
    (root / "state" / "ops").mkdir(parents=True, exist_ok=True)
    (root / "state" / "ops" / "latest.json").write_text(
        json.dumps({"action": "lineups-main", "window": "main",
                    "week": 1, "season": "2026", **fields}),
        encoding="utf-8")


def test_explicit_stage_and_week_beat_the_ops_file(tmp_path: Path, capsys):
    """A run driven by --stage/--week must not inherit whatever the last
    `daily_ops --write` decided.

    Before overrides existed, `office.py --stage waivers --week 5` called
    apply_gate with no arguments, and apply_gate read ops/latest.json — which
    on a Sunday says `lineups-main` for week 1. It would have applied the wrong
    stage for the wrong week and reported success.
    """
    import apply_gate

    _ops(tmp_path)
    apply_gate.main(["--root", str(tmp_path), "--action", "waivers",
                     "--week", "5", "--season", "2026", "--dry-run"])
    echoed = json.loads(capsys.readouterr().out.splitlines()[0])
    assert echoed["action"] == "waivers"
    assert echoed["week"] == 5


def test_ops_file_still_drives_the_daily_job(tmp_path: Path, capsys):
    """With no overrides the old behaviour is untouched."""
    import apply_gate

    _ops(tmp_path)
    apply_gate.main(["--root", str(tmp_path), "--dry-run"])
    echoed = json.loads(capsys.readouterr().out.splitlines()[0])
    assert echoed["action"] == "lineups-main"
    assert echoed["week"] == 1

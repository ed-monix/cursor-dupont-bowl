"""Tests for scripts/lib/apply_lineups.py — freeze vs fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.apply_lineups import apply_lineup_window
import lineups as lineups_cli

SIMPLE_SCORING = {"pass_yd": 0.04, "pass_td": 4, "rush_yd": 0.1, "rec": 0.5, "rec_yd": 0.1}

GAMES = [
    {"date": "2026-09-10", "home": "KC", "away": "LAC", "status": "pre_game", "week": 1},
    {"date": "2026-09-13", "home": "CHI", "away": "DET", "status": "pre_game", "week": 1},
]


def _players():
    return {
        "kelce": {"name": "Kelce", "pos": "TE", "team": "KC"},
        "otherte": {"name": "Other", "pos": "TE", "team": "CHI"},
        "qb": {"name": "QB", "pos": "QB", "team": "CHI"},
        "rb1": {"name": "RB1", "pos": "RB", "team": "CHI"},
        "rb2": {"name": "RB2", "pos": "RB", "team": "CHI"},
        "wr1": {"name": "WR1", "pos": "WR", "team": "CHI"},
        "wr2": {"name": "WR2", "pos": "WR", "team": "CHI"},
        "flex": {"name": "FLEX", "pos": "WR", "team": "CHI"},
        "k": {"name": "K", "pos": "K", "team": "CHI"},
        "dst": {"name": "DEF", "pos": "DEF", "team": "CHI"},
    }


def _starters(te="kelce"):
    return {
        "QB": "qb", "RB1": "rb1", "RB2": "rb2",
        "WR1": "wr1", "WR2": "wr2", "TE": te,
        "FLEX": "flex", "K": "k", "DEF": "dst",
    }


def _roster():
    return {
        "team": "t", "faab_remaining": 100,
        "starters": _starters(),
        "bench": ["otherte"], "ir": [],
    }


def test_illegal_lineup_falls_back_but_keeps_frozen_thursday_te():
    players = _players()
    roster = _roster()
    projections = {pid: {} for pid in players}
    legal = {"starters": _starters(), "justification": "lock TNF"}
    early = apply_lineup_window(
        {"t": roster}, players, projections, SIMPLE_SCORING,
        {"t": legal}, "early", GAMES, existing_lineups={},
    )
    assert early["lineups"]["t"]["locked_slots"]["TE"]["player_id"] == "kelce"
    # Illegal: TE and FLEX both kelce. Fallback must keep frozen Kelce.
    illegal = {
        "starters": {**_starters(), "FLEX": "kelce"},
        "justification": "oops",
    }
    main = apply_lineup_window(
        early["rosters"], players, projections, SIMPLE_SCORING,
        {"t": illegal}, "main", GAMES, existing_lineups=early["lineups"],
    )
    assert main["lineups"]["t"]["fallback"] is True
    assert main["lineups"]["t"]["starters"]["TE"] == "kelce"
    assert main["lineups"]["t"]["starters"]["FLEX"] != "kelce"


def test_legal_frozen_swap_is_not_fallback():
    players = _players()
    roster = _roster()
    projections = {pid: {} for pid in players}
    early = apply_lineup_window(
        {"t": roster}, players, projections, SIMPLE_SCORING,
        {"t": {"starters": _starters(), "justification": "early"}},
        "early", GAMES, existing_lineups={},
    )
    swapped = {
        "starters": _starters(te="otherte"),
        "justification": "bench the locked TE",
    }
    main = apply_lineup_window(
        early["rosters"], players, projections, SIMPLE_SCORING,
        {"t": swapped}, "main", GAMES, existing_lineups=early["lineups"],
    )
    report = main["report"]["teams"][0]
    assert report["freeze_violations"]
    assert report["fallback"] is False
    assert main["lineups"]["t"]["starters"]["TE"] == "kelce"


def test_lineups_cli_help():
    with pytest.raises(SystemExit) as exc:
        lineups_cli.main(["--help"])
    assert exc.value.code == 0


def test_lineups_cli_dry_run(tmp_path: Path):
    root = tmp_path
    week = root / "state" / "weeks" / "2026-w01"
    week.mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "scoring.json").write_text(json.dumps(SIMPLE_SCORING))
    (root / "teams" / "t").mkdir(parents=True)
    (root / "teams" / "t" / "roster.json").write_text(json.dumps(_roster()))
    (root / "state" / "players.json").write_text(json.dumps(_players()))
    (week / "projections.json").write_text(json.dumps({}))
    (week / "nfl-games.json").write_text(json.dumps(GAMES))
    decisions = {"t": {"starters": _starters(), "justification": "ok"}}
    dec_path = week / "canned.json"
    dec_path.write_text(json.dumps(decisions))
    rc = lineups_cli.main([
        "--root", str(root), "--week", "1", "--window", "early",
        "--decisions", str(dec_path), "--dry-run",
    ])
    assert rc == 0
    assert not (week / "lineups.json").exists()
    assert (week / "lineups-early-report.json").exists()

"""Tests for league_board.py."""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import league_board as lb


def test_resolve_player_none():
    """A None player_id resolves to None."""
    result = lb.resolve_player(None, {}, {}, {})
    assert result is None


def test_resolve_player_in_players():
    """A player_id in players.json is resolved with name/pos/nfl."""
    players = {
        "p1": {"name": "Alice", "pos": "QB", "team": "KC", "status": "Active", "injury": "Questionable"}
    }
    projections = {
        "p1": {"pass_yd": 250, "pass_td": 1}
    }
    scoring = {"pass_yd": 0.04, "pass_td": 4.0}

    result = lb.resolve_player("p1", players, projections, scoring)

    assert result["id"] == "p1"
    assert result["name"] == "Alice"
    assert result["pos"] == "QB"
    assert result["nfl"] == "KC"
    # proj_pts = 250 * 0.04 + 1 * 4 = 10 + 4 = 14.0
    assert result["proj_pts"] == 14.0
    assert result["status"] == "Active"
    assert result["injury"] == "Questionable"


def test_resolve_player_missing_from_players():
    """A player_id missing from players.json resolves with defaults."""
    players = {}
    projections = {}
    scoring = {}

    result = lb.resolve_player("p999", players, projections, scoring)

    assert result["id"] == "p999"
    assert result["name"] == "p999"
    assert result["pos"] == "?"
    assert result["nfl"] == "FA"
    assert result["proj_pts"] == 0.0


def test_resolve_player_no_projection():
    """A player with no projection scores 0.0."""
    players = {
        "p1": {"name": "Bob", "pos": "RB", "team": "TB"}
    }
    projections = {}
    scoring = {"rush_yd": 0.1}

    result = lb.resolve_player("p1", players, projections, scoring)

    assert result["id"] == "p1"
    assert result["name"] == "Bob"
    assert result["proj_pts"] == 0.0


def test_resolve_player_hand_computed_proj_pts():
    """proj_pts is correctly computed from projection and scoring."""
    players = {
        "p1": {"name": "Charlie", "pos": "WR", "team": "SF"}
    }
    projections = {
        "p1": {"rec": 8, "rec_yd": 120, "rec_td": 1}
    }
    scoring = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0}

    result = lb.resolve_player("p1", players, projections, scoring)

    # proj_pts = 8*0.5 + 120*0.1 + 1*6 = 4 + 12 + 6 = 22.0
    assert result["proj_pts"] == 22.0


def test_derive_league_board_starters_keyed_by_slot():
    """Starters are keyed by slot with resolved players or None."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 42,
            "starters": {"QB": "p1", "RB": "p2", "WR": None},
            "bench": [],
            "ir": [],
        }
    }
    players = {
        "p1": {"name": "Alice", "pos": "QB", "team": "KC"},
        "p2": {"name": "Bob", "pos": "RB", "team": "TB"},
    }
    projections = {
        "p1": {"pass_yd": 250},
        "p2": {"rush_yd": 80},
    }
    scoring = {"pass_yd": 0.04, "rush_yd": 0.1}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    assert "team1" in board
    assert "starters" in board["team1"]
    starters = board["team1"]["starters"]
    assert starters["QB"]["name"] == "Alice"
    assert starters["RB"]["name"] == "Bob"
    assert starters["WR"] is None


def test_derive_league_board_bench_and_ir_as_lists():
    """Bench and ir are lists of resolved player dicts."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 50,
            "starters": {"QB": "p1"},
            "bench": ["p2", "p3"],
            "ir": ["p4"],
        }
    }
    players = {
        "p1": {"name": "Alice", "pos": "QB", "team": "KC"},
        "p2": {"name": "Bob", "pos": "RB", "team": "TB"},
        "p3": {"name": "Charlie", "pos": "WR", "team": "SF"},
        "p4": {"name": "Dave", "pos": "TE", "team": "GB"},
    }
    projections = {}
    scoring = {}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    bench = board["team1"]["bench"]
    assert len(bench) == 2
    assert bench[0]["name"] == "Bob"
    assert bench[1]["name"] == "Charlie"

    ir = board["team1"]["ir"]
    assert len(ir) == 1
    assert ir[0]["name"] == "Dave"


def test_derive_league_board_faab_remaining_carried():
    """faab_remaining is carried through unchanged."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 23,
            "starters": {},
            "bench": [],
            "ir": [],
        },
        "team2": {
            "team": "Team Two",
            "faab_remaining": 99,
            "starters": {},
            "bench": [],
            "ir": [],
        },
    }
    players = {}
    projections = {}
    scoring = {}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    assert board["team1"]["faab_remaining"] == 23
    assert board["team2"]["faab_remaining"] == 99


def test_derive_league_board_multiple_teams():
    """Multiple teams are all included in the board."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 42,
            "starters": {"QB": "p1"},
            "bench": [],
            "ir": [],
        },
        "team2": {
            "team": "Team Two",
            "faab_remaining": 50,
            "starters": {"QB": "p2"},
            "bench": [],
            "ir": [],
        },
    }
    players = {
        "p1": {"name": "Alice", "pos": "QB", "team": "KC"},
        "p2": {"name": "Bob", "pos": "QB", "team": "TB"},
    }
    projections = {}
    scoring = {}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    assert len(board) == 2
    assert "team1" in board
    assert "team2" in board
    assert board["team1"]["starters"]["QB"]["name"] == "Alice"
    assert board["team2"]["starters"]["QB"]["name"] == "Bob"


def test_derive_league_board_missing_player_in_roster():
    """A player_id in a roster but missing from players.json resolves without raising."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 42,
            "starters": {"QB": "p_missing"},
            "bench": ["p_also_missing"],
            "ir": [],
        }
    }
    players = {}
    projections = {}
    scoring = {}

    # Should not raise
    board = lb.derive_league_board(rosters, players, projections, scoring)

    assert board["team1"]["starters"]["QB"]["id"] == "p_missing"
    assert board["team1"]["starters"]["QB"]["name"] == "p_missing"
    assert board["team1"]["starters"]["QB"]["pos"] == "?"
    assert board["team1"]["starters"]["QB"]["nfl"] == "FA"
    assert board["team1"]["starters"]["QB"]["proj_pts"] == 0.0

    bench = board["team1"]["bench"]
    assert len(bench) == 1
    assert bench[0]["id"] == "p_also_missing"


def test_derive_league_board_null_starter_stays_null():
    """A None starter slot remains None."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 42,
            "starters": {"QB": "p1", "RB": None, "FLEX": "p2"},
            "bench": [],
            "ir": [],
        }
    }
    players = {
        "p1": {"name": "Alice", "pos": "QB", "team": "KC"},
        "p2": {"name": "Bob", "pos": "RB", "team": "TB"},
    }
    projections = {}
    scoring = {}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    starters = board["team1"]["starters"]
    assert starters["QB"]["name"] == "Alice"
    assert starters["RB"] is None
    assert starters["FLEX"]["name"] == "Bob"


def test_derive_league_board_empty_rosters():
    """Empty rosters dict produces empty board."""
    board = lb.derive_league_board({}, {}, {}, {})
    assert board == {}


def test_derive_league_board_missing_roster_fields():
    """A roster missing starters/bench/ir defaults gracefully."""
    rosters = {
        "team1": {
            "team": "Team One",
            "faab_remaining": 42,
            # starters, bench, ir all missing
        }
    }
    players = {}
    projections = {}
    scoring = {}

    board = lb.derive_league_board(rosters, players, projections, scoring)

    assert board["team1"]["starters"] == {}
    assert board["team1"]["bench"] == []
    assert board["team1"]["ir"] == []
    assert board["team1"]["faab_remaining"] == 42


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

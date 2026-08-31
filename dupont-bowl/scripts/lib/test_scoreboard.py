"""Tests for scripts/scoreboard.py.

Hermetic (no network, no server bind). Tests the pure build_scoreboard_data()
and render_html() functions against fixture data, plus load_current_week().
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Import scoreboard module (follows the pattern from sync_sleeper/score_week tests).
scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(scripts_dir))
import scoreboard

# Fixture scores (computed by hand to verify).
# Using half-PPR config from config/scoring.default.json.


@pytest.fixture
def scoring() -> dict:
    """Half-PPR scoring config."""
    return {
        "pass_yd": 0.04,
        "pass_td": 4.0,
        "pass_int": -1.0,
        "rush_yd": 0.1,
        "rush_td": 6.0,
        "rec": 0.5,
        "rec_yd": 0.1,
        "rec_td": 6.0,
        "fum_lost": -2.0,
        "pts_allow_0": 10.0,
        "pts_allow_1_6": 7.0,
        "pts_allow_7_13": 4.0,
        "pts_allow_14_20": 1.0,
        "pts_allow_21_27": 0.0,
        "pts_allow_28_34": -1.0,
        "pts_allow_35p": -4.0,
        "sack": 1.0,
        "int": 2.0,
        "fum_rec": 2.0,
        "safe": 2.0,
        "blk_kick": 2.0,
        "st_td": 6.0,
        "fgm_0_19": 3.0,
        "fgm_20_29": 3.0,
        "fgm_30_39": 3.0,
        "fgm_40_49": 4.0,
        "fgm_50p": 5.0,
        "fgmiss": -1.0,
        "xpm": 1.0,
        "xpmiss": -1.0,
        "def_td": 6.0,
    }


@pytest.fixture
def players() -> dict:
    """Fixture player database."""
    return {
        "p1": {"name": "Patrick Mahomes", "pos": "QB", "team": "KC", "status": "Active", "injury": None},
        "p2": {"name": "Isiah Pacheco", "pos": "RB", "team": "KC", "status": "Active", "injury": None},
        "p3": {"name": "Travis Kelce", "pos": "TE", "team": "KC", "status": "Active", "injury": None},
        "p4": {"name": "Jalen Hurts", "pos": "QB", "team": "PHI", "status": "Active", "injury": None},
        "p5": {"name": "Saquon Barkley", "pos": "RB", "team": "PHI", "status": "Active", "injury": None},
        "p6": {"name": "DeVonta Smith", "pos": "WR", "team": "PHI", "status": "Active", "injury": None},
        "p7": {"name": "Jalen Waddle", "pos": "WR", "team": "MIA", "status": "Active", "injury": None},
        "p8": {"name": "Tyreek Hill", "pos": "WR", "team": "MIA", "status": "Active", "injury": None},
        "p9": {"name": "Josh Allen", "pos": "QB", "team": "BUF", "status": "Active", "injury": None},
        "p10": {"name": "Stefon Diggs", "pos": "WR", "team": "BUF", "status": "Active", "injury": None},
        "p11": {"name": "Lamar Jackson", "pos": "QB", "team": "BAL", "status": "Active", "injury": None},
        "p12": {"name": "Mark Andrews", "pos": "TE", "team": "BAL", "status": "Active", "injury": None},
    }


@pytest.fixture
def rosters() -> dict[str, dict]:
    """Fixture rosters for 12 teams (6 matchups, 2 per matchup)."""
    return {
        "chiefs": {
            "team": "chiefs",
            "faab_remaining": 50,
            "starters": {"QB": "p1", "RB1": "p2", "RB2": None, "WR1": None, "WR2": None, "TE": "p3", "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "eagles": {
            "team": "eagles",
            "faab_remaining": 75,
            "starters": {"QB": "p4", "RB1": "p5", "RB2": None, "WR1": "p6", "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "dolphins": {
            "team": "dolphins",
            "faab_remaining": 40,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": "p7", "WR2": "p8", "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "bills": {
            "team": "bills",
            "faab_remaining": 60,
            "starters": {"QB": "p9", "RB1": None, "RB2": None, "WR1": "p10", "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "ravens": {
            "team": "ravens",
            "faab_remaining": 55,
            "starters": {"QB": "p11", "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": "p12", "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "patriots": {
            "team": "patriots",
            "faab_remaining": 45,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "broncos": {
            "team": "broncos",
            "faab_remaining": 50,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "chargers": {
            "team": "chargers",
            "faab_remaining": 55,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "raiders": {
            "team": "raiders",
            "faab_remaining": 50,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "seahawks": {
            "team": "seahawks",
            "faab_remaining": 50,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "cowboys": {
            "team": "cowboys",
            "faab_remaining": 50,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "niners": {
            "team": "niners",
            "faab_remaining": 50,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None, "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
    }


@pytest.fixture
def stats() -> dict:
    """Fixture stats for week 1. Hand-computed scores below."""
    return {
        # Chiefs matchup
        "p1": {"pass_yd": 250, "pass_td": 2, "pass_int": 0},  # 250*0.04 + 2*4.0 = 10 + 8 = 18.0
        "p2": {"rush_yd": 75, "rush_td": 1},  # 75*0.1 + 1*6.0 = 7.5 + 6 = 13.5
        "p3": {"rec": 5, "rec_yd": 60, "rec_td": 1},  # 5*0.5 + 60*0.1 + 1*6.0 = 2.5 + 6 + 6 = 14.5
        # Chiefs total: 18.0 + 13.5 + 14.5 = 46.0
        # Eagles matchup
        "p4": {"pass_yd": 300, "pass_td": 1, "pass_int": 1},  # 300*0.04 + 1*4.0 - 1*1.0 = 12 + 4 - 1 = 15.0
        "p5": {"rush_yd": 100, "rush_td": 0},  # 100*0.1 = 10.0
        "p6": {"rec": 8, "rec_yd": 80, "rec_td": 1},  # 8*0.5 + 80*0.1 + 1*6.0 = 4 + 8 + 6 = 18.0
        # Eagles total: 15.0 + 10.0 + 18.0 = 43.0
        # Dolphins matchup (p7, p8 have stats; QB is None, so Dolphins total)
        "p7": {"rec": 10, "rec_yd": 150, "rec_td": 1},  # 10*0.5 + 150*0.1 + 1*6.0 = 5 + 15 + 6 = 26.0
        "p8": {"rec": 8, "rec_yd": 120, "rec_td": 0},  # 8*0.5 + 120*0.1 = 4 + 12 = 16.0
        # Dolphins total: 26.0 + 16.0 = 42.0
        # Bills matchup (p9, p10 have stats)
        "p9": {"pass_yd": 280, "pass_td": 2, "pass_int": 0},  # 280*0.04 + 2*4.0 = 11.2 + 8 = 19.2
        "p10": {"rec": 12, "rec_yd": 140, "rec_td": 2},  # 12*0.5 + 140*0.1 + 2*6.0 = 6 + 14 + 12 = 32.0
        # Bills total: 19.2 + 32.0 = 51.2
        # Ravens matchup (p11, p12 have stats)
        "p11": {"pass_yd": 320, "pass_td": 2, "pass_int": 0},  # 320*0.04 + 2*4.0 = 12.8 + 8 = 20.8
        "p12": {"rec": 6, "rec_yd": 70, "rec_td": 0},  # 6*0.5 + 70*0.1 = 3 + 7 = 10.0
        # Ravens total: 20.8 + 10.0 = 30.8
    }


@pytest.fixture
def schedule() -> dict:
    """Fixture schedule with 6 matchups for week 1."""
    return {
        "regular_season": {
            "1": [
                ["chiefs", "eagles"],
                ["dolphins", "bills"],
                ["ravens", "patriots"],
                ["broncos", "chargers"],
                ["raiders", "seahawks"],
                ["cowboys", "niners"],
            ],
            "2": [],
        },
        "playoffs": {},
    }


def test_build_scoreboard_with_fixture_data(schedule, rosters, stats, players, scoring):
    """Build scoreboard from fixture and verify correct totals and leader flags."""
    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)

    assert board["week"] == 1
    assert len(board["matchups"]) == 6

    # Verify matchup 1: chiefs (46.0) vs eagles (43.0) -> chiefs lead.
    m1 = board["matchups"][0]
    assert m1["matchup_id"] == 1
    assert m1["home_team"]["slug"] == "chiefs"
    assert m1["away_team"]["slug"] == "eagles"
    assert m1["home_team"]["total"] == pytest.approx(46.0, abs=0.01)
    assert m1["away_team"]["total"] == pytest.approx(43.0, abs=0.01)
    assert m1["leader_slug"] == "chiefs"

    # Verify matchup 2: dolphins (42.0) vs bills (51.2) -> bills lead.
    m2 = board["matchups"][1]
    assert m2["matchup_id"] == 2
    assert m2["home_team"]["slug"] == "dolphins"
    assert m2["away_team"]["slug"] == "bills"
    assert m2["home_team"]["total"] == pytest.approx(42.0, abs=0.01)
    assert m2["away_team"]["total"] == pytest.approx(51.2, abs=0.01)
    assert m2["leader_slug"] == "bills"

    # Verify matchup 3: ravens (30.8) vs patriots (0.0, no starters with stats).
    m3 = board["matchups"][2]
    assert m3["matchup_id"] == 3
    assert m3["home_team"]["slug"] == "ravens"
    assert m3["away_team"]["slug"] == "patriots"
    assert m3["home_team"]["total"] == pytest.approx(30.8, abs=0.01)
    assert m3["away_team"]["total"] == pytest.approx(0.0, abs=0.01)
    assert m3["leader_slug"] == "ravens"

    # Remaining matchups have no rostered starters with stats.
    for i in range(3, 6):
        m = board["matchups"][i]
        assert m["home_team"]["total"] == pytest.approx(0.0, abs=0.01)
        assert m["away_team"]["total"] == pytest.approx(0.0, abs=0.01)
        assert m["leader_slug"] is None  # Tied at 0


def test_starters_yet_to_play_count(schedule, rosters, stats, players, scoring):
    """Verify 'starters yet to play' count is correct."""
    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)

    # Matchup 1: chiefs
    m1 = board["matchups"][0]
    # Chiefs starters: QB(p1-has stats), RB1(p2-has stats), RB2(None), WR1(None),
    # WR2(None), TE(p3-has stats), FLEX(None), K(None), DEF(None)
    # Starters yet to play: RB2, WR1, WR2, FLEX, K, DEF = 6 (or fewer if None is not counted)
    # Actually: only filled slots with None are still-empty; unfilled (None) are not starters.
    # Chiefs roster has only 3 filled starter slots: QB, RB1, TE. All 3 have stats.
    # So yet_to_play = 0.
    assert m1["home_team"]["starters_yet_to_play"] == 0
    # Eagles: QB(p4), RB1(p5), WR1(p6) all have stats. Rest are None (unfilled).
    # So yet_to_play = 0.
    assert m1["away_team"]["starters_yet_to_play"] == 0

    # Matchup 3: ravens vs patriots
    m3 = board["matchups"][2]
    # Ravens: QB(p11-has stats), TE(p12-has stats). All filled starters have stats.
    assert m3["home_team"]["starters_yet_to_play"] == 0
    # Patriots: no filled starters.
    assert m3["away_team"]["starters_yet_to_play"] == 0


def test_starters_yet_to_play_with_missing_stats(schedule, players, scoring):
    """Verify 'yet to play' counts a starter with no stats row."""
    # Fixture: matchup with starters that have no stats entries.
    rosters = {
        "team_a": {
            "team": "team_a",
            "faab_remaining": 100,
            "starters": {"QB": "p1", "RB1": "p2", "TE": "p3", "WR1": None, "RB2": None, "WR2": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "team_b": {
            "team": "team_b",
            "faab_remaining": 100,
            "starters": {"QB": "p4", "RB1": "p5", "TE": "p6", "WR1": None, "RB2": None, "WR2": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
    }
    schedule = {
        "regular_season": {"1": [["team_a", "team_b"]]},
        "playoffs": {},
    }
    # Only p1, p4 have stats. p2, p3, p5, p6 are missing.
    stats = {
        "p1": {"pass_yd": 200},
        "p4": {"pass_yd": 250},
    }

    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)

    m = board["matchups"][0]
    # team_a: QB(p1-has stats), RB1(p2-missing), TE(p3-missing) -> 2 yet to play.
    assert m["home_team"]["starters_yet_to_play"] == 2
    # team_b: QB(p4-has stats), RB1(p5-missing), TE(p6-missing) -> 2 yet to play.
    assert m["away_team"]["starters_yet_to_play"] == 2


def test_api_scores_json_structure(schedule, rosters, stats, players, scoring):
    """Verify the /api/scores JSON structure is what the HTML renders from."""
    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)

    # The JSON structure should be exactly what build_scoreboard_data returns.
    assert "week" in board
    assert "matchups" in board
    assert isinstance(board["matchups"], list)

    for m in board["matchups"]:
        assert "matchup_id" in m
        assert "home_team" in m
        assert "away_team" in m
        assert "leader_slug" in m
        assert "home_team" in m
        assert "away_team" in m

        for team_key in ["home_team", "away_team"]:
            team = m[team_key]
            assert "slug" in team
            assert "total" in team
            assert "scores" in team
            assert "starters_yet_to_play" in team
            assert "roster" in team


def test_render_html_basic(schedule, rosters, stats, players, scoring):
    """Verify render_html produces valid HTML with team names and scores."""
    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)
    html = scoreboard.render_html(board, players)

    assert "<!DOCTYPE html>" in html
    assert "<meta http-equiv=\"refresh\"" in html
    assert "Week 1" in html
    assert "chiefs" in html.lower()
    assert "eagles" in html.lower()
    assert "46.0" in html  # Chiefs total
    assert "43.0" in html  # Eagles total
    # Leader's team row should carry the "win" class.
    assert 'class="row win"' in html


def test_render_html_playoff_bracket_guards_seed_placeholders(scoring, players):
    """Verify scoreboard gracefully skips playoff seeds without rosters."""
    # Fixture: playoff week with seed placeholders.
    rosters = {
        "team_a": {
            "team": "team_a",
            "faab_remaining": 100,
            "starters": {"QB": "p1", "RB1": None, "TE": None, "WR1": None, "RB2": None, "WR2": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
        "team_b": {
            "team": "team_b",
            "faab_remaining": 100,
            "starters": {"QB": "p2", "RB1": None, "TE": None, "WR1": None, "RB2": None, "WR2": None, "FLEX": None, "K": None, "DEF": None},
            "bench": [],
            "ir": [],
        },
    }
    schedule = {
        "regular_season": {},
        "playoffs": {
            "15": [
                ["team_a", "seed_3"],  # seed_3 is not yet set.
                ["team_b", "seed_4"],
            ],
        },
    }
    stats = {
        "p1": {"pass_yd": 200},
        "p2": {"pass_yd": 250},
    }

    week = 15
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)

    # Both matchups should be skipped (contain seed placeholders).
    assert len(board["matchups"]) == 0


def test_player_line_html_with_name_pos_team(schedule, rosters, stats, players, scoring):
    """Verify HTML includes player name, position, NFL team, and points."""
    week = 1
    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)
    html = scoreboard.render_html(board, players)

    # Check for specific player details in HTML (name + "pos · team" meta).
    # p1: Patrick Mahomes, QB, KC
    assert "Patrick Mahomes" in html
    assert "QB · KC" in html
    # p3: Travis Kelce, TE, KC
    assert "Travis Kelce" in html
    assert "TE · KC" in html


def test_empty_scoreboard_renders(scoring, players):
    """Verify empty scoreboard (no matchups) renders without error."""
    schedule = {"regular_season": {"1": []}, "playoffs": {}}
    rosters = {}
    stats = {}
    week = 1

    board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, week)
    html = scoreboard.render_html(board, players)

    assert "<!DOCTYPE html>" in html
    assert "Week 1" in html
    # No matchups -> the empty-state message, no matchup cards.
    assert "class=\"empty-state\"" in html
    assert "class=\"card\"" not in html


# Tests for load_current_week() — bug fix and hardening.

def test_load_current_week_from_list_completed():
    """official_weeks = [1,2,3] -> returns next week (4)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": [1, 2, 3]}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            assert week == 4


def test_load_current_week_from_empty_list():
    """official_weeks = [] or missing standings -> returns 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": []}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            assert week == 1


def test_load_current_week_missing_standings():
    """Missing standings.json -> returns 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        # No standings.json created

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            assert week == 1


def test_load_current_week_capped_at_17():
    """official_weeks at week 17 -> stays capped at 17."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            # max([1..17]) = 17, so min(17+1, 17) = 17 (capped)
            assert week == 17


def test_load_current_week_malformed_dict():
    """official_weeks is a dict (malformed) -> returns 1, no exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": {"1": "done", "2": "done"}}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            assert week == 1


def test_load_current_week_malformed_string():
    """official_weeks is a string (malformed) -> returns 1, no exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": "1,2,3"}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            assert week == 1


def test_load_current_week_list_with_non_int():
    """official_weeks is a list but contains non-int -> returns 1, no exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        standings_path = state_dir / "standings.json"
        standings_path.write_text(json.dumps({"official_weeks": [1, 2, "three", 4]}))

        with mock.patch.object(scoreboard, "STATE_DIR", state_dir):
            week = scoreboard.load_current_week(2026)
            # int("three") raises ValueError, guard catches it and returns 1
            assert week == 1

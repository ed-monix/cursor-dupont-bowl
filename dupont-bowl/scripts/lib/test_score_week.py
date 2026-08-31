"""Tests for scripts/score_week.py.

Fixtures: 12 teams (12 rosters), two weeks of stats (2x6 matchups),
scoring config, and expected standings including the points-for tiebreaker.

Hand-computed expected values for standings verification:
- Week 1 results and cumulative
- Week 2 results and cumulative
- Tiebreaker scenario: two teams with identical W/L/T but different PF

All stat values and expected points are computed by hand to verify the
score_week logic against the pure scoring functions.
"""

import json
import tempfile
from pathlib import Path

import pytest

# Import pure logic functions we're testing (not the CLI)
# We'll import them from the scripts directory since test lives in lib/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from score_week import (
    fold_week_into_standings,
    fold_if_not_official,
    mark_week_official,
    score_matchup,
    load_schedule,
)

# Also import schedule_gen for integration test
from lib.schedule_gen import generate as generate_schedule


@pytest.fixture
def scoring() -> dict:
    """Half-PPR scoring config (from config/scoring.default.json)."""
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
        "sack": 1.0,
        "int": 2.0,
        "fum_rec": 2.0,
        "safe": 2.0,
        "pts_allow_0": 10.0,
        "pts_allow_1_6": 7.0,
        "pts_allow_7_13": 4.0,
        "pts_allow_14_20": 1.0,
        "pts_allow_21_27": 0.0,
        "pts_allow_28_34": -1.0,
        "pts_allow_35p": -4.0,
    }


@pytest.fixture
def team_rosters() -> dict:
    """12 team rosters with minimal starters."""
    rosters = {}
    for i in range(1, 13):
        slug = f"team-{i:02d}"
        # Each team has two "players": one QB and one RB.
        # The player IDs are team_specific, e.g., team-01-QB, team-01-RB
        rosters[slug] = {
            "team": slug,
            "faab_remaining": 100,
            "starters": {
                "QB": f"p-{slug}-qb",
                "RB1": f"p-{slug}-rb1",
                "RB2": None,  # Empty slots are allowed
                "WR1": None,
                "WR2": None,
                "TE": None,
                "FLEX": None,
                "K": None,
                "DEF": None,
            },
            "bench": [],
            "ir": [],
        }
    return rosters


@pytest.fixture
def week1_stats() -> dict:
    """Week 1 stats for all players.

    Each team has a QB and RB1. QBs throw for ~200 yards + 1 TD.
    RBs rush for ~50 yards + 1 TD. This gives realistic point totals.

    Hand-computed expected points per team:
      QB: 200*0.04 + 1*4 = 8 + 4 = 12.0
      RB: 50*0.1  + 1*6 = 5 + 6 = 11.0
      Team total: 23.0

    (All teams get the same stats this week for simplicity in matchup testing.)
    """
    stats = {}
    for i in range(1, 13):
        slug = f"team-{i:02d}"
        qb_id = f"p-{slug}-qb"
        rb_id = f"p-{slug}-rb1"

        stats[qb_id] = {
            "pass_yd": 200,
            "pass_td": 1,
            "pass_int": 0,
        }
        stats[rb_id] = {
            "rush_yd": 50,
            "rush_td": 1,
            "fum_lost": 0,
        }

    return stats


@pytest.fixture
def week2_stats() -> dict:
    """Week 2 stats: some variation to create different point totals.

    This is used to create a tiebreaker scenario and test standings updates.

    Design:
    - Teams 1-6: same as week 1 (23.0 points each)
    - Teams 7-12: slightly different (20.0 points each)
      QB: 180*0.04 + 1*4 = 7.2 + 4 = 11.2
      RB: 45*0.1  + 1*6 = 4.5 + 6 = 10.5
      Total: 21.7 (rounded; let's make it cleaner)

    Actually, let's make it:
    - Teams 1-6: 24.0 points (200 pass_yd, 1 pass_td, 60 rush_yd, 1 rush_td)
    - Teams 7-12: 20.0 points (200 pass_yd, 1 pass_td, 40 rush_yd, 0 rush_td)
      Teams 7-12: QB 200*0.04 + 1*4 = 12.0, RB 40*0.1 = 4.0, total 16.0

    Better:
    - Teams 1-6: QB 200*0.04 + 1*4 = 12, RB 50*0.1 + 1*6 = 11, total 23
    - Teams 7-9: QB 200*0.04 + 1*4 = 12, RB 40*0.1 + 1*6 = 10, total 22
    - Teams 10-12: QB 200*0.04 + 1*4 = 12, RB 30*0.1 + 1*6 = 9, total 21
    """
    stats = {}

    # Teams 1-6: 23 points (same as week 1)
    for i in range(1, 7):
        slug = f"team-{i:02d}"
        stats[f"p-{slug}-qb"] = {"pass_yd": 200, "pass_td": 1, "pass_int": 0}
        stats[f"p-{slug}-rb1"] = {"rush_yd": 50, "rush_td": 1, "fum_lost": 0}

    # Teams 7-9: 22 points
    for i in range(7, 10):
        slug = f"team-{i:02d}"
        stats[f"p-{slug}-qb"] = {"pass_yd": 200, "pass_td": 1, "pass_int": 0}
        stats[f"p-{slug}-rb1"] = {"rush_yd": 40, "rush_td": 1, "fum_lost": 0}

    # Teams 10-12: 21 points
    for i in range(10, 13):
        slug = f"team-{i:02d}"
        stats[f"p-{slug}-qb"] = {"pass_yd": 200, "pass_td": 1, "pass_int": 0}
        stats[f"p-{slug}-rb1"] = {"rush_yd": 30, "rush_td": 1, "fum_lost": 0}

    return stats


@pytest.fixture
def schedule_w1() -> list:
    """Week 1 matchups: 6 teams per group, 3 matchups per group.

    Matchups:
    1. team-01 (home) vs team-02 (away)
    2. team-03 (home) vs team-04 (away)
    3. team-05 (home) vs team-06 (away)
    4. team-07 (home) vs team-08 (away)
    5. team-09 (home) vs team-10 (away)
    6. team-11 (home) vs team-12 (away)
    """
    return [
        ["team-01", "team-02"],
        ["team-03", "team-04"],
        ["team-05", "team-06"],
        ["team-07", "team-08"],
        ["team-09", "team-10"],
        ["team-11", "team-12"],
    ]


@pytest.fixture
def schedule_w2() -> list:
    """Week 2 matchups: different pairings to vary outcomes."""
    return [
        ["team-01", "team-03"],
        ["team-02", "team-04"],
        ["team-05", "team-07"],
        ["team-06", "team-08"],
        ["team-09", "team-11"],
        ["team-10", "team-12"],
    ]


def test_score_matchup_tie(team_rosters, week1_stats, scoring):
    """Test scoring when both teams have identical lineups (tie)."""
    # Both teams have the same stats, so they should tie.
    matchup = score_matchup(
        "team-01",
        "team-02",
        team_rosters["team-01"],
        team_rosters["team-02"],
        week1_stats,
        scoring,
    )

    # Both should score 23.0 (12 QB + 11 RB)
    assert matchup["home"] == "team-01"
    assert matchup["away"] == "team-02"
    assert matchup["home_score"] == pytest.approx(23.0, abs=0.01)
    assert matchup["away_score"] == pytest.approx(23.0, abs=0.01)
    assert matchup["winner"] == "tie"
    assert "home_lineup" in matchup
    assert "away_lineup" in matchup
    assert matchup["home_lineup"][f"p-team-01-qb"] == pytest.approx(12.0, abs=0.01)
    assert matchup["home_lineup"][f"p-team-01-rb1"] == pytest.approx(11.0, abs=0.01)


def test_score_week1_all_matchups(team_rosters, week1_stats, scoring, schedule_w1):
    """Score all 6 matchups of week 1 (where all teams have identical stats)."""
    matchups = []
    for home, away in schedule_w1:
        matchup = score_matchup(
            home, away, team_rosters[home], team_rosters[away], week1_stats, scoring
        )
        matchups.append(matchup)

    # All 6 matchups should be ties (all teams have 23.0 points)
    assert len(matchups) == 6
    for matchup in matchups:
        assert matchup["home_score"] == pytest.approx(23.0, abs=0.01)
        assert matchup["away_score"] == pytest.approx(23.0, abs=0.01)
        assert matchup["winner"] == "tie"


def test_fold_week1_standings(team_rosters, week1_stats, scoring, schedule_w1):
    """Fold week 1 matchups into standings.

    Expected after week 1 (all ties):
    - Each team: W=0, L=0, T=1, PF=23.0, PA=23.0
    """
    # Score all matchups
    matchups = []
    for home, away in schedule_w1:
        matchup = score_matchup(
            home, away, team_rosters[home], team_rosters[away], week1_stats, scoring
        )
        matchups.append(matchup)

    # Fold into standings
    standings = fold_week_into_standings({}, matchups, week=1)

    # Verify all 12 teams exist with correct records
    assert len(standings["teams"]) == 12
    for i in range(1, 13):
        slug = f"team-{i:02d}"
        assert slug in standings["teams"]
        team_record = standings["teams"][slug]
        assert team_record["wins"] == 0
        assert team_record["losses"] == 0
        assert team_record["ties"] == 1
        assert team_record["points_for"] == pytest.approx(23.0, abs=0.01)
        assert team_record["points_against"] == pytest.approx(23.0, abs=0.01)


def test_fold_week2_standings_with_variation(
    team_rosters, week2_stats, scoring, schedule_w2
):
    """Fold week 2 matchups into standings.

    This week has point variation:
    - Teams 1-6: 23 points
    - Teams 7-9: 22 points
    - Teams 10-12: 21 points

    Week 1 (from schedule_w1): all teams score 23, so all matchups are ties.
    After week 1, every team has 0-0-1 (all ties).

    Week 2 matchups (schedule_w2):
    1. team-01 (23) vs team-03 (23) -> tie
    2. team-02 (23) vs team-04 (23) -> tie
    3. team-05 (23) vs team-07 (22) -> team-05 wins
    4. team-06 (23) vs team-08 (22) -> team-06 wins
    5. team-09 (22) vs team-11 (21) -> team-09 wins
    6. team-10 (21) vs team-12 (21) -> tie

    After both weeks:
    - team-01: W/L/T = 0/0/2 (tie week 1, tie week 2), PF=46.0
    - team-02: W/L/T = 0/0/2 (tie week 1, tie week 2), PF=46.0
    - team-03: W/L/T = 0/1/1 (tie week 1, loss week 2), PF=46.0
    - team-04: W/L/T = 0/1/1 (tie week 1, loss week 2), PF=46.0
    - team-05: W/L/T = 1/0/1 (tie week 1, win week 2), PF=46.0
    - team-06: W/L/T = 1/0/1 (tie week 1, win week 2), PF=46.0
    - team-07: W/L/T = 0/1/1 (tie week 1, loss week 2), PF=45.0
    - team-08: W/L/T = 0/1/1 (tie week 1, loss week 2), PF=45.0
    - team-09: W/L/T = 1/0/1 (tie week 1, win week 2), PF=45.0
    - team-10: W/L/T = 0/0/2 (tie week 1, tie week 2), PF=44.0
    - team-11: W/L/T = 0/1/1 (tie week 1, loss week 2), PF=44.0
    - team-12: W/L/T = 0/0/2 (tie week 1, tie week 2), PF=42.0
    """
    # First, fold week 1 into standings
    week1_matchups = []
    schedule_w1_data = [
        ["team-01", "team-02"],
        ["team-03", "team-04"],
        ["team-05", "team-06"],
        ["team-07", "team-08"],
        ["team-09", "team-10"],
        ["team-11", "team-12"],
    ]
    week1_stats_data = {}
    for i in range(1, 13):
        slug = f"team-{i:02d}"
        week1_stats_data[f"p-{slug}-qb"] = {"pass_yd": 200, "pass_td": 1}
        week1_stats_data[f"p-{slug}-rb1"] = {"rush_yd": 50, "rush_td": 1}

    for home, away in schedule_w1_data:
        matchup = score_matchup(
            home, away, team_rosters[home], team_rosters[away], week1_stats_data, scoring
        )
        week1_matchups.append(matchup)

    standings = fold_week_into_standings({}, week1_matchups, week=1)

    # Now score week 2 matchups
    week2_matchups = []
    for home, away in schedule_w2:
        matchup = score_matchup(
            home, away, team_rosters[home], team_rosters[away], week2_stats, scoring
        )
        week2_matchups.append(matchup)

    # Fold week 2 into standings
    standings = fold_week_into_standings(standings, week2_matchups, week=2)

    # Verify standings (after both weeks)
    # Week 1 matchups (all tied at 23 points each):
    # ["team-01", "team-02"], ["team-03", "team-04"], ["team-05", "team-06"],
    # ["team-07", "team-08"], ["team-09", "team-10"], ["team-11", "team-12"]
    # After week 1: all teams have 0-0-1
    #
    # Week 2 matchups from schedule_w2 (with point variation):
    # ["team-01", "team-03"] -> 23 vs 23 -> tie
    # ["team-02", "team-04"] -> 23 vs 23 -> tie
    # ["team-05", "team-07"] -> 23 vs 22 -> team-05 wins
    # ["team-06", "team-08"] -> 23 vs 22 -> team-06 wins
    # ["team-09", "team-11"] -> 22 vs 21 -> team-09 wins
    # ["team-10", "team-12"] -> 21 vs 21 -> tie
    expected = {
        "team-01": {"wins": 0, "losses": 0, "ties": 2, "points_for": 46.0},
        "team-02": {"wins": 0, "losses": 0, "ties": 2, "points_for": 46.0},
        "team-03": {"wins": 0, "losses": 0, "ties": 2, "points_for": 46.0},
        "team-04": {"wins": 0, "losses": 0, "ties": 2, "points_for": 46.0},
        "team-05": {"wins": 1, "losses": 0, "ties": 1, "points_for": 46.0},
        "team-06": {"wins": 1, "losses": 0, "ties": 1, "points_for": 46.0},
        "team-07": {"wins": 0, "losses": 1, "ties": 1, "points_for": 45.0},
        "team-08": {"wins": 0, "losses": 1, "ties": 1, "points_for": 45.0},
        "team-09": {"wins": 1, "losses": 0, "ties": 1, "points_for": 45.0},
        "team-10": {"wins": 0, "losses": 0, "ties": 2, "points_for": 44.0},
        "team-11": {"wins": 0, "losses": 1, "ties": 1, "points_for": 44.0},
        "team-12": {"wins": 0, "losses": 0, "ties": 2, "points_for": 44.0},
    }

    for slug, exp in expected.items():
        assert slug in standings["teams"], f"Team {slug} missing from standings"
        record = standings["teams"][slug]
        assert record["wins"] == exp["wins"], f"{slug}: wins mismatch"
        assert record["losses"] == exp["losses"], f"{slug}: losses mismatch"
        assert record["ties"] == exp["ties"], f"{slug}: ties mismatch"
        assert record["points_for"] == pytest.approx(
            exp["points_for"], abs=0.01
        ), f"{slug}: points_for mismatch"


def test_points_for_tiebreaker(team_rosters, scoring):
    """Test that standings correctly tracks points_for when W/L/T are equal.

    Create two teams with identical records (1-1-0) but different points_for.
    This tests that the standings correctly accumulate PF for tiebreaker purposes.

    Team A:
    - Week 1: wins 100-90 (PF=100, PA=90)
    - Week 2: loses 105-110 (PF=105, PA=110)
    - Total: 1-1-0, PF=205, PA=200

    Team B:
    - Week 1: loses 90-100 (PF=90, PA=100)
    - Week 2: wins 120-115 (PF=120, PA=115)
    - Total: 1-1-0, PF=210, PA=215

    Both have 1-1-0 records, but team-b has higher PF (210 vs 205).
    """
    matchups = [
        # Week 1
        {
            "home": "team-a",
            "away": "team-other-1",
            "home_score": 100.0,
            "away_score": 90.0,
            "home_lineup": {"p1": 100.0},
            "away_lineup": {"p2": 90.0},
            "winner": "team-a",
        },
        {
            "home": "team-other-2",
            "away": "team-b",
            "home_score": 100.0,
            "away_score": 90.0,
            "home_lineup": {"p3": 100.0},
            "away_lineup": {"p4": 90.0},
            "winner": "team-other-2",
        },
        # Week 2
        {
            "home": "team-other-3",
            "away": "team-a",
            "home_score": 110.0,
            "away_score": 105.0,
            "home_lineup": {"p5": 110.0},
            "away_lineup": {"p6": 105.0},
            "winner": "team-other-3",
        },
        {
            "home": "team-b",
            "away": "team-other-4",
            "home_score": 120.0,
            "away_score": 115.0,
            "home_lineup": {"p7": 120.0},
            "away_lineup": {"p8": 115.0},
            "winner": "team-b",
        },
    ]

    standings = fold_week_into_standings({}, matchups, week=1)

    # Both team-a and team-b should have 1-1-0 record
    assert standings["teams"]["team-a"]["wins"] == 1
    assert standings["teams"]["team-a"]["losses"] == 1
    assert standings["teams"]["team-a"]["ties"] == 0
    assert standings["teams"]["team-a"]["points_for"] == pytest.approx(205.0, abs=0.01)
    assert standings["teams"]["team-a"]["points_against"] == pytest.approx(200.0, abs=0.01)

    assert standings["teams"]["team-b"]["wins"] == 1
    assert standings["teams"]["team-b"]["losses"] == 1
    assert standings["teams"]["team-b"]["ties"] == 0
    assert standings["teams"]["team-b"]["points_for"] == pytest.approx(210.0, abs=0.01)
    assert standings["teams"]["team-b"]["points_against"] == pytest.approx(215.0, abs=0.01)

    # team-b has higher PF (210 vs 205), which is the tiebreaker.
    # (Standings structure doesn't enforce sort order, but records are correct.)


def test_idempotency_mark_week_official():
    """Test that marking a week official twice produces identical standings."""
    standings = {"teams": {}, "season": 2026}

    # Mark week 5 official
    standings1 = mark_week_official(standings, week=5, season=2026)
    # Mark it again
    standings2 = mark_week_official(standings1, week=5, season=2026)

    # Both should be identical
    assert standings1 == standings2
    assert standings1["official_weeks"] == [5]
    assert standings2["official_weeks"] == [5]


def test_idempotency_fold_if_not_official(team_rosters, week2_stats, scoring, schedule_w2):
    """Test that fold_if_not_official is truly idempotent (no double-counting).

    This tests the real AC: calling fold_if_not_official twice with the same
    standings and matchups produces the same result as calling once. The guard
    logic prevents double-folding when week is already official.
    """
    # Create initial standings (as if week 1 was already folded)
    initial_standings = {
        "season": 2026,
        "teams": {
            "team-01": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-02": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-03": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-04": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-05": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-06": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-07": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-08": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-09": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-10": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-11": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
            "team-12": {"wins": 0, "losses": 0, "ties": 1, "points_for": 23.0, "points_against": 23.0},
        },
    }

    # Score week 2 matchups
    week2_matchups = []
    for home, away in schedule_w2:
        matchup = score_matchup(
            home, away, team_rosters[home], team_rosters[away], week2_stats, scoring
        )
        week2_matchups.append(matchup)

    # Apply fold_if_not_official once
    standings1 = fold_if_not_official(
        json.loads(json.dumps(initial_standings)), week2_matchups, week=2, season=2026
    )

    # Apply fold_if_not_official again on the SAME standings (now official)
    # This should not change anything (no double-count)
    standings2 = fold_if_not_official(
        standings1, week2_matchups, week=2, season=2026
    )

    # Both should be identical: calling twice yields same result as once
    assert standings1 == standings2, "fold_if_not_official should be idempotent"
    assert 2 in standings2.get("official_weeks", []), "Week 2 should be marked official"


def test_load_schedule_with_schedule_gen():
    """Integration test: load_schedule reads real schedule_gen.py output shape.

    schedule_gen produces:
    {"regular_season": {"1": [...], ..., "14": [...]},
     "playoffs": {"15": [...], "16": [...], "17": [...]}}

    This test confirms load_schedule works against that real contract.
    """
    import tempfile

    # Generate a real schedule for 12 teams
    team_slugs = [f"team-{i:02d}" for i in range(1, 13)]
    real_schedule = generate_schedule(team_slugs, seed=42)

    # Write it to a temp file and load it through load_schedule
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(real_schedule, f)
        temp_path = Path(f.name)

    try:
        # Test regular season weeks
        for week in range(1, 15):
            matchups = load_schedule(temp_path, week)
            assert len(matchups) == 6, f"Week {week} should have 6 matchups"
            # All teams should be real slugs, not placeholders
            for home, away in matchups:
                assert home in team_slugs, f"Week {week}: {home} not a real team slug"
                assert away in team_slugs, f"Week {week}: {away} not a real team slug"

        # Test playoff weeks (should filter out unresolved placeholders)
        # Weeks 15-17 have placeholders like "seed_3", "winner_15_1" which should be skipped
        for week in range(15, 18):
            matchups = load_schedule(temp_path, week)
            # Playoff template has 2, 2, 1 matchups respectively, but with placeholders
            # Our filter should return empty list or only resolved pairs
            # Since no games have been played, all are placeholders -> empty
            assert len(matchups) == 0, f"Week {week} should have 0 resolvable matchups (all placeholders)"

    finally:
        temp_path.unlink()


def test_cli_help():
    """Test that the CLI can be invoked with --help."""
    # This is a smoke test; we can't easily test the full CLI without
    # setting up a temp directory structure, but we can verify the script
    # is syntactically correct.
    import subprocess
    result = subprocess.run(
        ["python3", "/home/user/dupont-bowl/dupont-bowl/scripts/score_week.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--week" in result.stdout
    assert "--final" in result.stdout

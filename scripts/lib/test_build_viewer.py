"""Tests for scripts/build_viewer.py pure mappers. No I/O, no network."""

import build_viewer


PLAYERS = {
    "p1": {"name": "Star QB", "pos": "QB", "team": "KC"},
    "p2": {"name": "Bell Cow", "pos": "RB", "team": "DET"},
    "p3": {"name": "Bye Week WR", "pos": "WR", "team": "BUF"},
}


def make_team(slug, total, scores, stat_lines, starters):
    return {"slug": slug, "roster": {"starters": starters}, "scores": scores,
            "stat_lines": stat_lines, "total": total, "starters_yet_to_play": 0}


def test_viewer_starters_marks_played_and_carries_meta():
    team = make_team(
        "dynamos", 24.0,
        scores={"p1": 20.0, "p2": 4.0, "p3": 0.0},
        stat_lines={"p1": {"pass_yd": 300, "pass_td": 2}, "p2": {"rush_yd": 40}},
        starters={"QB": "p1", "RB1": "p2", "WR1": "p3", "WR2": None})
    rows = build_viewer.viewer_starters(team, PLAYERS)
    by = {r["slot"]: r for r in rows}
    assert "WR2" not in by                       # null slot omitted
    assert by["QB"]["played"] is True
    assert by["QB"]["name"] == "Star QB" and by["QB"]["nfl"] == "KC"
    assert "300" in by["QB"]["stat"]             # stat summary present
    assert by["WR1"]["played"] is False          # no stat line -> yet to play
    assert by["WR1"]["stat"] == ""


def test_viewer_matchup_maps_leader_slug_to_side():
    home = make_team("dynamos", 100.0, {"p1": 100.0}, {"p1": {"pass_yd": 250}}, {"QB": "p1"})
    away = make_team("wagon", 80.0, {"p2": 80.0}, {"p2": {"rush_yd": 120}}, {"RB1": "p2"})
    m = {"home_team": home, "away_team": away, "leader_slug": "dynamos"}
    v = build_viewer.viewer_matchup(m, PLAYERS, {"dynamos": "3-0", "wagon": "1-2"})
    assert v["leader"] == "home"
    assert v["home"]["name"] == "Dynamos" and v["home"]["record"] == "3-0"
    assert v["away"]["name"] == "Wagon"

    m_tie = {"home_team": home, "away_team": away, "leader_slug": None}
    assert build_viewer.viewer_matchup(m_tie, PLAYERS, {})["leader"] is None


def test_viewer_standings_sorted_by_record_then_points_for():
    standings_json = {"teams": {
        "a": {"wins": 2, "losses": 1, "ties": 0, "points_for": 300.0, "points_against": 280.0},
        "b": {"wins": 2, "losses": 1, "ties": 0, "points_for": 320.0, "points_against": 275.0},
        "c": {"wins": 3, "losses": 0, "ties": 0, "points_for": 290.0, "points_against": 250.0},
    }}
    rows = build_viewer.viewer_standings(standings_json)
    # c leads (3 wins); then b over a (same record, higher PF).
    assert [r["slug"] for r in rows] == ["c", "b", "a"]
    assert rows[1]["pf"] == 320.0


def test_pretty_name():
    assert build_viewer.pretty("last-place-luxury") == "Last Place Luxury"

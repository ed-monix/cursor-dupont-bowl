"""Commissioner daily ops from the NFL slate."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from lib.daily_ops import decide, ops_for_root, wake_targets, week_for_date

REPO = Path(__file__).resolve().parents[2]

TNF = [
    {"date": "2026-09-10", "status": "pre_game", "week": 1, "home": "LAR", "away": "SF"},
    {"date": "2026-09-13", "status": "pre_game", "week": 1, "home": "DET", "away": "CHI"},
    {"date": "2026-09-14", "status": "pre_game", "week": 1, "home": "KC", "away": "DEN"},
]


def test_waivers_before_first_kickoff():
    call = decide(
        today=date(2026, 9, 8),
        week_games=TNF,
        done={"waivers": False, "lineups-early": False, "lineups-main": False, "recap": False},
    )
    assert call["action"] == "waivers"


def test_gameday_thursday_is_early_lineups():
    call = decide(
        today=date(2026, 9, 10),
        week_games=TNF,
        done={"waivers": True, "lineups-early": False, "lineups-main": False, "recap": False},
    )
    assert call["action"] == "lineups-early"
    assert call["window"] == "early"
    assert call["games_today"][0]["home"] == "LAR"


def test_gameday_sunday_is_main_lineups():
    call = decide(
        today=date(2026, 9, 13),
        week_games=TNF,
        done={"waivers": True, "lineups-early": True, "lineups-main": False, "recap": False},
    )
    assert call["action"] == "lineups-main"
    assert call["window"] == "main"


def test_idle_when_window_already_run():
    call = decide(
        today=date(2026, 9, 10),
        week_games=TNF,
        done={"waivers": True, "lineups-early": True, "lineups-main": False, "recap": False},
    )
    assert call["action"] == "idle"


def test_recap_when_slate_complete():
    done_games = [{**g, "status": "complete"} for g in TNF]
    call = decide(
        today=date(2026, 9, 15),
        week_games=done_games,
        done={"waivers": True, "lineups-early": True, "lineups-main": True, "recap": False},
    )
    assert call["action"] == "recap"


def test_kicked_games_today_do_not_reopen_lineups():
    games = [
        {"date": "2026-09-10", "status": "complete", "week": 1, "home": "LAR", "away": "SF"},
        {"date": "2026-09-13", "status": "pre_game", "week": 1, "home": "DET", "away": "CHI"},
    ]
    call = decide(
        today=date(2026, 9, 10),
        week_games=games,
        done={"waivers": True, "lineups-early": False, "lineups-main": False, "recap": False},
    )
    assert call["action"] == "idle"


def test_week_for_date_picks_gameday_week():
    assert week_for_date(TNF, date(2026, 9, 10)) == 1
    assert week_for_date(TNF, date(2026, 9, 8)) == 1


def test_wake_skips_owned_teams():
    from lib import grok_bots
    roster = grok_bots.load_roster(REPO)
    wake = wake_targets("lineups-early", roster)
    assert "your-team" not in wake["grok_bots"]
    assert "wifes-team" not in wake["grok_bots"]
    assert "costanza" in wake["grok_bots"]
    assert wake["cursor"] == ["your-team", "wifes-team"]
    assert len(wake["grok_bots"]) == 10


def test_ops_for_committed_repo_thursday_week1():
    call = ops_for_root(REPO, today=date(2026, 9, 10), season="2026")
    assert call["week"] == 1
    # TNF LAR/SF is already complete in committed state → idle or early
    # depending on remaining pre_game Thursday games (none).
    assert call["action"] in ("idle", "lineups-early")

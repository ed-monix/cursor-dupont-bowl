"""Classify NFL games into lineup windows (PLAN.md §4 lineups).

Sleeper's undocumented schedule feed is a list of
`{status, date, home, week, game_id, away}`. Windows are by kickoff DATE,
not by fantasy-command weekday:

- **early**: any game whose local date is Tuesday–Saturday (TNF, WTF
  kickoff, Friday, Saturday internationals).
- **main**: Sunday and Monday (the rest of the slate, including MNF).

A team's GM may still change a starter whose NFL game has not yet been
locked by a completed window and has not kicked off (`status` still
`pre_game`). Scripts decide which slots are frozen; agents do not.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional, Union


WINDOWS = ("early", "main")

# Mon=0 ... Sun=6. Tue–Sat are the "set this before they kick" window.
_EARLY_WEEKDAYS = {1, 2, 3, 4, 5}

_KICKED_STATUSES = {"in_game", "complete", "final", "closed"}


def parse_game_date(value: Any) -> Optional[date]:
    """Parse Sleeper's `YYYY-MM-DD` (or datetime prefix) into a date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def window_for_date(game_date: Optional[date]) -> str:
    """Return 'early' or 'main' for a calendar date. Unknown -> main."""
    if game_date is None:
        return "main"
    if game_date.weekday() in _EARLY_WEEKDAYS:
        return "early"
    return "main"


def window_for_game(game: dict) -> str:
    return window_for_date(parse_game_date(game.get("date")))


def game_has_kicked(game: Optional[dict]) -> bool:
    if not game:
        return False
    status = str(game.get("status") or "").lower()
    if status in _KICKED_STATUSES:
        return True
    return False


def games_for_week(schedule: list, week: Union[int, str]) -> list:
    """Filter a full-season schedule list to one NFL week."""
    try:
        week_i = int(week)
    except (TypeError, ValueError):
        return []
    out = []
    for game in schedule or []:
        if not isinstance(game, dict):
            continue
        try:
            if int(game.get("week")) == week_i:
                out.append(game)
        except (TypeError, ValueError):
            continue
    return out


def index_games_by_team(games: list) -> dict:
    """NFL team abbrev -> game dict for this week (one game per team)."""
    by_team = {}
    for game in games or []:
        if not isinstance(game, dict):
            continue
        for side in ("home", "away"):
            team = game.get(side)
            if isinstance(team, str) and team:
                by_team[team] = game
        # DST player_ids are the team abbrev itself.
    return by_team


def lookup_game(nfl_team: Optional[str], by_team: dict) -> Optional[dict]:
    if not nfl_team:
        return None
    return by_team.get(str(nfl_team))


def annotate_player_game(player: dict, by_team: dict) -> dict:
    """Copy of a resolved player with this week's NFL game + window attached.

    `player` is a league-board row `{id, name, pos, nfl, proj_pts, ...}`.
    """
    row = dict(player)
    nfl = row.get("nfl")
    game = lookup_game(nfl, by_team)
    if not game:
        row["game"] = None
        row["window"] = "main"
        row["kicked"] = False
        return row
    row["game"] = {
        "date": game.get("date"),
        "status": game.get("status"),
        "home": game.get("home"),
        "away": game.get("away"),
        "game_id": game.get("game_id"),
    }
    row["window"] = window_for_game(game)
    row["kicked"] = game_has_kicked(game)
    return row


def compact_week_games(games: list) -> list:
    """Trim schedule rows for a GM pack (no extra Sleeper keys)."""
    compact = []
    for game in games or []:
        if not isinstance(game, dict):
            continue
        compact.append({
            "date": game.get("date"),
            "status": game.get("status"),
            "home": game.get("home"),
            "away": game.get("away"),
            "week": game.get("week"),
            "window": window_for_game(game),
        })
    compact.sort(key=lambda g: (str(g.get("date") or ""), str(g.get("home") or "")))
    return compact

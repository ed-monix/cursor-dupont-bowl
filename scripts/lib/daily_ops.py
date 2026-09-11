"""Decide today's league op from the NFL slate. Scripts decide facts.

The Commissioner Bot runs a daily check. It does not invent the calendar:
this module says whether to idle, run waivers, lock a lineup window, or recap.
The Commissioner clones this repo, runs this module, wakes other Bots,
and is the only Bot that writes back to git. GMs never touch the repo.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional, Union

from lib import grok_bots, nfl_slate

ACTIONS = ("idle", "waivers", "lineups-early", "lineups-main", "recap")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def load_all_games(root: Union[str, Path], season: str = "2026") -> list:
    root = Path(root)
    games = []
    weeks = root / "state" / "weeks"
    if not weeks.is_dir():
        return games
    for child in sorted(weeks.iterdir()):
        if not child.name.startswith(f"{season}-w"):
            continue
        payload = _read_json(child / "nfl-games.json", [])
        if isinstance(payload, list):
            games.extend(payload)
    return games


def week_for_date(games: list, today: date) -> Optional[int]:
    on_today = []
    upcoming = []
    past = []
    for game in games or []:
        if not isinstance(game, dict):
            continue
        try:
            week = int(game.get("week"))
        except (TypeError, ValueError):
            continue
        gd = nfl_slate.parse_game_date(game.get("date"))
        if gd is None:
            continue
        if gd == today:
            on_today.append(week)
        elif gd >= today:
            upcoming.append((gd, week))
        else:
            past.append(week)
    if on_today:
        return min(on_today)
    if upcoming:
        upcoming.sort()
        return upcoming[0][1]
    if past:
        return max(past)
    return None


def games_in_week(games: list, week: int) -> list:
    return nfl_slate.games_for_week(games, week)


def week_dir(root: Path, season: str, week: int) -> Path:
    return root / "state" / "weeks" / f"{season}-w{week:02d}"


def done_flags(root: Path, season: str, week: int) -> dict:
    folder = week_dir(root, season, week)
    lineups = _read_json(folder / "lineups.json", {})
    windows = set()
    if isinstance(lineups, dict):
        for entry in lineups.values():
            if isinstance(entry, dict):
                for w in entry.get("windows_run") or []:
                    windows.add(w)
    return {
        "waivers": (folder / "faab-report.json").is_file(),
        "lineups-early": "early" in windows,
        "lineups-main": "main" in windows,
        "recap": (folder / "recap.md").is_file(),
    }


def first_kickoff(week_games: list) -> Optional[date]:
    dates = []
    for game in week_games:
        gd = nfl_slate.parse_game_date(game.get("date"))
        if gd:
            dates.append(gd)
    return min(dates) if dates else None


def all_complete(week_games: list) -> bool:
    if not week_games:
        return False
    return all(nfl_slate.game_has_kicked(g) for g in week_games)


def decide(
    *,
    today: date,
    week_games: list,
    done: dict,
) -> dict[str, Any]:
    """Return an ops call. Public slate only — no GM files."""
    kickoff = first_kickoff(week_games)
    today_games = [
        g for g in week_games
        if nfl_slate.parse_game_date(g.get("date")) == today
    ]
    pending_today = [g for g in today_games if not nfl_slate.game_has_kicked(g)]

    if pending_today:
        windows = {nfl_slate.window_for_game(g) for g in pending_today}
        if "early" in windows and not done.get("lineups-early"):
            return _call("lineups-early", "early", today, pending_today, kickoff)
        if "main" in windows and not done.get("lineups-main"):
            return _call("lineups-main", "main", today, pending_today, kickoff)

    if kickoff is not None and today < kickoff and not done.get("waivers"):
        return _call("waivers", None, today, week_games, kickoff)

    if all_complete(week_games) and not done.get("recap"):
        return _call("recap", None, today, week_games, kickoff)

    return _call("idle", None, today, week_games, kickoff)


def _call(action: str, window: Optional[str], today: date, games: list,
          kickoff: Optional[date]) -> dict[str, Any]:
    compact = nfl_slate.compact_week_games(today_games_only(games, today, action))
    return {
        "action": action,
        "window": window,
        "today": today.isoformat(),
        "first_kickoff": kickoff.isoformat() if kickoff else None,
        "games_today": compact,
        "reason": _reason(action, window, today, kickoff),
    }


def today_games_only(games: list, today: date, action: str) -> list:
    if action not in ("lineups-early", "lineups-main"):
        return []
    return [
        g for g in games
        if nfl_slate.parse_game_date(g.get("date")) == today
    ]


def _reason(action: str, window: Optional[str], today: date,
            kickoff: Optional[date]) -> str:
    if action == "idle":
        return f"{today.isoformat()}: no league op"
    if action == "waivers":
        return f"before first kickoff {kickoff}; waivers still open"
    if action.startswith("lineups"):
        return f"gameday {today.isoformat()} window {window}; pending kickoffs"
    return f"slate complete; recap missing"


def celebrity_slugs(roster: dict) -> list[str]:
    out = []
    for role in grok_bots.gm_roles(roster):
        slug = role.get("slug")
        if not slug or slug in grok_bots.OWNED_SLUGS:
            continue
        if role.get("product") != "grok_bot":
            continue
        out.append(slug)
    return out


def wake_targets(action: str, roster: dict) -> dict[str, list[str]]:
    """Who the Commissioner pings. Owned GMs stay on Cursor."""
    gms = celebrity_slugs(roster) if roster else []
    owned = list(grok_bots.OWNED_SLUGS)
    if action == "idle":
        return {"grok_bots": [], "cursor": [], "also": []}
    if action == "waivers":
        return {"grok_bots": gms, "cursor": owned, "also": ["scout", "media"]}
    if action in ("lineups-early", "lineups-main"):
        return {"grok_bots": gms, "cursor": owned, "also": []}
    if action == "recap":
        return {"grok_bots": [], "cursor": [], "also": ["commissioner"]}
    return {"grok_bots": [], "cursor": [], "also": []}


def ops_for_root(
    root: Union[str, Path],
    *,
    today: date,
    season: str = "2026",
) -> dict[str, Any]:
    root = Path(root)
    games = load_all_games(root, season)
    week = week_for_date(games, today)
    if week is None:
        call = _call("idle", None, today, [], None)
        call.update(week=None, season=season, wake=wake_targets("idle", {}))
        return call
    week_games = games_in_week(games, week)
    done = done_flags(root, season, week)
    call = decide(today=today, week_games=week_games, done=done)
    roster = grok_bots.load_roster(root)
    call.update(
        week=week,
        season=season,
        done=done,
        wake=wake_targets(call["action"], roster),
    )
    return call


def ops_dir(root: Path) -> Path:
    return Path(root) / "state" / "ops"


def write_ops(root: Union[str, Path], call: dict) -> Path:
    """Commissioner gate: persist today's ops call into the league repo."""
    root = Path(root)
    dest_dir = ops_dir(root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    day = call.get("today") or date.today().isoformat()
    payload = dict(call)
    payload.setdefault("gate", {"received": {}, "rejected": {}})
    dest = dest_dir / f"{day}.json"
    text = json.dumps(payload, indent=2) + "\n"
    dest.write_text(text, encoding="utf-8")
    (dest_dir / "latest.json").write_text(text, encoding="utf-8")
    return dest

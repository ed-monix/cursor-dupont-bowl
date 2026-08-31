#!/usr/bin/env python3
"""scoreboard.py — live game-day matchup board on http://localhost:8080

IMPLEMENTATION NOTE: Originally specified as Flask app, but Flask cannot be
installed in this environment (PyPI egress blocked). Implemented using Python
standard library only: http.server (BaseHTTPRequestHandler + ThreadingHTTPServer)
plus threading for the poll loop. Same behavior, zero external dependencies.

BUILD AGENT: implement per TASKS.md 4.1. Spec:

- Background thread polls Sleeper weekly stats every 45s on game days
  (any rostered starter's NFL team plays today), every 10 min otherwise.
  Isolate the fetch behind `fetch_week_stats(season, week) -> dict` so the
  source can be swapped if the unofficial endpoint changes.
- Scoring: reuse scripts/lib/scoring.py against config/scoring.json.
- Route "/": current week's 6 matchups from state/schedule.json +
  teams/*/roster.json. Each card: team names, live totals, per-starter line
  (name, pos, NFL team, pts), count of starters yet to play, leader highlight.
  <meta http-equiv="refresh" content="60"> is acceptable v1.
- Route "/api/scores": the JSON the page renders (useful for debugging).
- CLI: --week N (default: current from state/standings.json), --port.
- This board is entertainment; Monday's score_week.py --final is official.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

# Reuse the approved scoring library.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from lib.scoring import score_lineup

# Configuration.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
STATE_DIR = REPO_ROOT / "state"
TEAMS_DIR = REPO_ROOT / "teams"


def load_json(path: Path, default: Any = None) -> Any:
    """Load JSON from a file, or return default if missing."""
    if not path.exists():
        return default if default is not None else {}
    with open(path) as f:
        return json.load(f)


def fetch_week_stats(season: int, week: int) -> dict:
    """Fetch weekly stats from Sleeper API with fallback to on-disk cache.

    Attempts to fetch stats from the unofficial Sleeper endpoint:
    https://api.sleeper.app/v1/stats/nfl/regular/<season>/<week>

    On any network failure or HTTP error, falls back to reading the on-disk
    state/weeks/<season>-w<NN>/stats.json if present. If neither source is
    available, returns {} (the scoreboard will render with zeros for all
    players until stats arrive).

    Args:
        season: NFL season (e.g. 2026)
        week: Week number (1-17)

    Returns:
        dict mapping player_id (str) to stat_line (dict), or {} if unavailable.
    """
    url = f"https://api.sleeper.app/v1/stats/nfl/regular/{season}/{week}"

    try:
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        # Network error, timeout, or malformed response. Fall back to disk cache.
        pass

    # Fallback: read on-disk cache.
    week_path = STATE_DIR / "weeks" / f"{season}-w{week:02d}" / "stats.json"
    cached = load_json(week_path, {})
    return cached


def load_scoring_config() -> dict:
    """Load scoring config, dropping underscore-prefixed keys."""
    scoring_path = CONFIG_DIR / "scoring.json"
    if scoring_path.exists():
        raw = load_json(scoring_path, {})
    else:
        raw = load_json(CONFIG_DIR / "scoring.default.json", {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_current_week(season: int) -> int:
    """Load current week from state/standings.json, or return next uncompleted week.

    Reads official_weeks from standings.json, which score_week.py writes as a
    list of completed week ints (e.g. [1, 2, 3]). Returns the next week after
    the last completed one, capped at 17. If official_weeks is empty, absent,
    or malformed, returns 1. Never raises an exception.

    Args:
        season: NFL season (e.g. 2026). Currently unused; kept for future
                per-season tracking.

    Returns:
        int in range [1, 17], representing the week to display on the live board.
    """
    standings_path = STATE_DIR / "standings.json"
    standings = load_json(standings_path, {})

    # official_weeks is written by score_week.py as a list of completed week ints.
    # e.g. [1, 2, 3] means weeks 1-3 are final; board should show week 4.
    official_weeks = standings.get("official_weeks")

    # Guard: must be a list. Non-list values (dict, string, None) fall back to 1.
    if not isinstance(official_weeks, list):
        return 1

    # Guard: must contain only ints. Any non-int or malformed value falls back.
    try:
        weeks_int = [int(w) for w in official_weeks]
    except (ValueError, TypeError):
        return 1

    # If empty list, no weeks completed yet; show week 1.
    if not weeks_int:
        return 1

    # Next week after the max completed, capped at 17 (playoff cutoff).
    return min(max(weeks_int) + 1, 17)


def build_scoreboard_data(
    schedule: dict,
    rosters_dict: dict[str, dict],
    stats: dict,
    players: dict,
    scoring: dict,
    week: int,
) -> dict:
    """Build the scoreboard data structure from schedule, rosters, stats, scoring.

    Pure function, no I/O or network. Testable offline.

    Args:
        schedule: {regular_season: {"1": [["home", "away"], ...], ...}, playoffs: {...}}
        rosters_dict: {team_slug: roster_json, ...}
        stats: {player_id: stat_line, ...}
        players: {player_id: {name, pos, team, status, injury}, ...}
        scoring: {stat_key: points_per_unit, ...}
        week: Current week number to render.

    Returns:
        {
            week: int,
            matchups: [
                {
                    week: int,
                    matchup_id: int,  # 1-6 for regular season
                    home_team: {
                        roster: roster_json,
                        scores: {player_id: points, "total": float},
                        total: float,
                        starters_yet_to_play: int,
                    },
                    away_team: { ... },
                    leader_slug: str,  # "home" or "away" or None if tied
                },
                ...
            ],
        }
    """
    matchups_out = []

    # Determine if we're in playoffs (week >= 15) or regular season.
    schedule_key = "playoffs" if week >= 15 else "regular_season"
    week_matchups = schedule.get(schedule_key, {}).get(str(week), [])

    for matchup_id, (home_slug, away_slug) in enumerate(week_matchups, start=1):
        # Guard: if a playoff seed hasn't been set yet (e.g. "seed_3"), skip it.
        if home_slug.startswith("seed_") or away_slug.startswith("seed_"):
            continue

        home_roster = rosters_dict.get(home_slug, {})
        away_roster = rosters_dict.get(away_slug, {})

        home_scores = score_lineup(home_roster, stats, scoring)
        away_scores = score_lineup(away_roster, stats, scoring)

        home_total = home_scores.get("total", 0.0)
        away_total = away_scores.get("total", 0.0)

        # Determine leader.
        if home_total > away_total:
            leader_slug = home_slug
        elif away_total > home_total:
            leader_slug = away_slug
        else:
            leader_slug = None  # Tied

        # Count starters yet to play (starters with no entry in stats).
        home_starters = home_roster.get("starters", {})
        away_starters = away_roster.get("starters", {})

        home_yet_to_play = sum(
            1 for pid in home_starters.values()
            if pid is not None and pid not in stats
        )
        away_yet_to_play = sum(
            1 for pid in away_starters.values()
            if pid is not None and pid not in stats
        )

        # Raw stat line per starter that has one (a player absent here has not
        # played yet). Lets the render show the production behind the points,
        # so a viewer can tell whether the board is in sync with the latest.
        home_stat_lines = {
            pid: stats[pid] for pid in home_starters.values()
            if pid is not None and pid in stats
        }
        away_stat_lines = {
            pid: stats[pid] for pid in away_starters.values()
            if pid is not None and pid in stats
        }

        matchup = {
            "week": week,
            "matchup_id": matchup_id,
            "home_team": {
                "slug": home_slug,
                "roster": home_roster,
                "scores": home_scores,
                "total": home_total,
                "starters_yet_to_play": home_yet_to_play,
                "stat_lines": home_stat_lines,
            },
            "away_team": {
                "slug": away_slug,
                "roster": away_roster,
                "scores": away_scores,
                "total": away_total,
                "starters_yet_to_play": away_yet_to_play,
                "stat_lines": away_stat_lines,
            },
            "leader_slug": leader_slug,
        }
        matchups_out.append(matchup)

    return {
        "week": week,
        "matchups": matchups_out,
    }


def _stat_summary(pos: str, s: dict) -> str:
    """Compact human-readable stat line for one player, so a viewer can see the
    production behind the points (and tell whether it's in sync with the latest).
    Empty for a player with no stats yet."""
    if not s:
        return ""

    def n(k):
        return int(round(s.get(k, 0) or 0))

    parts = []
    if pos == "QB":
        if n("pass_yd") or n("pass_td"):
            parts.append(f'{n("pass_yd")} pass yd')
        if n("pass_td"):
            parts.append(f'{n("pass_td")} pass TD')
        if n("pass_int"):
            parts.append(f'{n("pass_int")} INT')
        if n("rush_yd"):
            parts.append(f'{n("rush_yd")} rush yd')
        if n("rush_td"):
            parts.append(f'{n("rush_td")} rush TD')
    elif pos == "RB":
        if n("rush_yd") or n("rush_td"):
            parts.append(f'{n("rush_yd")} rush yd')
        if n("rush_td"):
            parts.append(f'{n("rush_td")} TD')
        if n("rec"):
            parts.append(f'{n("rec")} rec, {n("rec_yd")} yd')
        if n("rec_td"):
            parts.append(f'{n("rec_td")} rec TD')
    elif pos in ("WR", "TE"):
        if n("rec") or n("rec_yd"):
            parts.append(f'{n("rec")} rec, {n("rec_yd")} yd')
        if n("rec_td"):
            parts.append(f'{n("rec_td")} TD')
        if n("rush_yd"):
            parts.append(f'{n("rush_yd")} rush yd')
    elif pos == "K":
        fg = n("fgm_0_19") + n("fgm_20_29") + n("fgm_30_39") + n("fgm_40_49") + n("fgm_50p")
        if fg:
            parts.append(f'{fg} FG')
        if n("xpm"):
            parts.append(f'{n("xpm")} XP')
    elif pos == "DEF":
        if "pts_allow" in s:
            parts.append(f'{n("pts_allow")} pa')
        if n("sack"):
            parts.append(f'{n("sack")} sk')
        if n("int"):
            parts.append(f'{n("int")} INT')
        if n("fum_rec"):
            parts.append(f'{n("fum_rec")} FR')
        if n("def_td"):
            parts.append(f'{n("def_td")} TD')
    return ", ".join(parts)


def _side_html(team: dict, players: dict, state: str, badge: str) -> str:
    """One team's column: header (name over score) then its starters, each with
    a stat line. `state` is 'win' | 'lose' | 'tie'; `badge` is the sub-header
    line (e.g. 'Leading by 12.4' or '2 yet to play')."""
    from html import escape

    starters = team["roster"].get("starters", {})
    scores = team["scores"]
    stat_lines = team.get("stat_lines", {})

    rows = ""
    for slot, pid in starters.items():
        if pid is None:
            rows += (
                '<div class="p out"><span class="slot">'
                f'{escape(str(slot))}</span><span class="pmid"><span class="pn">—</span></span>'
                '<span class="pp">·</span></div>'
            )
            continue
        info = players.get(pid, {})
        name = escape(str(info.get("name", pid)))
        pos = str(info.get("pos", "?"))
        nfl = escape(str(info.get("team") or "FA"))
        pts = scores.get(pid, 0.0)
        played = pid in stat_lines
        if played:
            stat = escape(_stat_summary(pos, stat_lines[pid])) or "in play"
            pp = f'{pts:.1f}'
            out_cls = ""
        else:
            stat = "yet to play"
            pp = "–"
            out_cls = " out"
        rows += (
            f'<div class="p{out_cls}">'
            f'<span class="slot">{escape(str(slot))}</span>'
            f'<span class="pmid"><span class="pn">{name} <span class="meta">{escape(pos)} · {nfl}</span></span>'
            f'<span class="stat">{stat}</span></span>'
            f'<span class="pp">{pp}</span>'
            '</div>'
        )

    return (
        f'<div class="side {state}">'
        '<div class="head">'
        f'<span class="tn">{escape(str(team["slug"]))}</span>'
        f'<span class="ts">{team["total"]:.1f}</span>'
        '</div>'
        f'<div class="sub">{badge}</div>'
        f'<div class="players">{rows}</div>'
        '</div>'
    )


def render_html(scoreboard_data: dict, players: dict) -> str:
    """Render scoreboard data as a clean, minimal, theme-aware HTML page.

    Two columns per matchup — each team's name and score sit directly over that
    team's players, each with a stat line. The leader is emphasized (tinted
    column, accent score, winning margin). No framework, no external assets
    (system fonts only), so it renders instantly and works offline on localhost.

    Args:
        scoreboard_data: Output of build_scoreboard_data().
        players: {player_id: {name, pos, team, status, injury}, ...}

    Returns:
        HTML string with <meta http-equiv="refresh" content="60">.
    """
    from html import escape

    week = scoreboard_data["week"]
    matchups = scoreboard_data["matchups"]

    def badge(team, is_leader, is_tie, margin):
        bits = []
        if is_leader:
            bits.append(f'<span class="lead">Leading by {margin:.1f}</span>')
        elif is_tie:
            bits.append('<span class="lead tieflag">Tied</span>')
        ytp = team["starters_yet_to_play"]
        if ytp:
            bits.append(f'<span class="ytp">{ytp} yet to play</span>')
        return "".join(bits) or "&nbsp;"

    cards = ""
    for m in matchups:
        home, away = m["home_team"], m["away_team"]
        leader = m["leader_slug"]
        is_tie = leader is None
        margin = abs(home["total"] - away["total"])

        home_state = "win" if leader == home["slug"] else ("tie" if is_tie else "lose")
        away_state = "win" if leader == away["slug"] else ("tie" if is_tie else "lose")

        cards += (
            '<section class="card">'
            + _side_html(home, players, home_state,
                         badge(home, home_state == "win", is_tie, margin))
            + _side_html(away, players, away_state,
                         badge(away, away_state == "win", is_tie, margin))
            + '</section>'
        )

    if not cards:
        cards = '<p class="empty-state">No matchups scheduled for this week yet.</p>'

    updated = datetime.now().strftime("%a %-I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>The DuPont Bowl · Week {week}</title>
  <style>
    :root {{
      --bg:#fafaf9; --card:#fff; --line:#eceae6; --text:#18181b;
      --muted:#9a9a93; --faint:#c2c2bb; --accent:#1f7a4d; --winbg:#f3f8f4;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg:#111110; --card:#1a1a18; --line:#2a2a26; --text:#eeeeea;
        --muted:#83837c; --faint:#4f4f48; --accent:#59c793; --winbg:#17251d;
      }}
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; background:var(--bg); color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      font-size:15px; line-height:1.4; -webkit-font-smoothing:antialiased;
    }}
    .wrap {{ max-width:720px; margin:0 auto; padding:40px 20px 64px; }}
    header {{ display:flex; align-items:baseline; justify-content:space-between;
      margin-bottom:24px; padding-bottom:16px; border-bottom:1px solid var(--line); }}
    .brand {{ font-weight:600; letter-spacing:.14em; text-transform:uppercase; font-size:13px; }}
    .wk {{ color:var(--muted); font-size:13px; letter-spacing:.04em; }}
    .card {{ display:grid; grid-template-columns:1fr 1fr; background:var(--card);
      border:1px solid var(--line); border-radius:12px; overflow:hidden; margin-bottom:12px; }}
    .side {{ padding:16px 18px; }}
    .side + .side {{ border-left:1px solid var(--line); }}
    .side.win {{ background:var(--winbg); box-shadow:inset 0 2px 0 var(--accent); }}
    .head {{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }}
    .tn {{ text-transform:uppercase; letter-spacing:.06em; font-size:14px;
      color:var(--muted); font-weight:500; overflow:hidden; text-overflow:ellipsis;
      white-space:nowrap; }}
    .ts {{ font-variant-numeric:tabular-nums; font-size:24px; font-weight:400;
      color:var(--muted); }}
    .side.win .tn {{ color:var(--text); font-weight:700; }}
    .side.win .ts {{ color:var(--accent); font-weight:700; font-size:28px; }}
    .sub {{ min-height:15px; margin:2px 0 12px; font-size:11px; letter-spacing:.02em; }}
    .lead {{ color:var(--accent); font-weight:600; }}
    .lead.tieflag {{ color:var(--muted); font-weight:500; }}
    .ytp {{ color:var(--faint); margin-left:8px; }}
    .players {{ border-top:1px solid var(--line); padding-top:4px; }}
    .p {{ display:grid; grid-template-columns:30px 1fr auto; column-gap:8px;
      align-items:baseline; padding:5px 0; }}
    .slot {{ color:var(--faint); font-size:10px; letter-spacing:.06em;
      text-transform:uppercase; }}
    .pmid {{ min-width:0; }}
    .pn {{ display:block; font-size:13px; white-space:nowrap; overflow:hidden;
      text-overflow:ellipsis; }}
    .pn .meta {{ color:var(--faint); font-size:11px; }}
    .stat {{ display:block; color:var(--muted); font-size:10.5px; letter-spacing:.01em;
      white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .pp {{ font-variant-numeric:tabular-nums; font-size:13px; color:var(--text); }}
    .p.out .pn, .p.out .pp {{ color:var(--faint); }}
    .p.out .stat {{ color:var(--faint); font-style:italic; }}
    footer {{ margin-top:24px; text-align:center; color:var(--faint); font-size:11px;
      letter-spacing:.03em; }}
    .empty-state {{ color:var(--muted); text-align:center; padding:40px 0; }}
    @media (max-width:560px) {{
      .card {{ grid-template-columns:1fr; }}
      .side + .side {{ border-left:none; border-top:1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <span class="brand">The DuPont Bowl</span>
      <span class="wk">Week {week}</span>
    </header>
    {cards}
    <footer>Live · refreshes every 60s · updated {escape(updated)} · unofficial until Monday</footer>
  </div>
</body>
</html>"""


# Thread-safe scoreboard cache.
_scoreboard_data: dict | None = None
_scoreboard_lock = threading.Lock()
_poll_stop_event = threading.Event()


def get_cached_scoreboard() -> dict | None:
    """Thread-safe getter for cached scoreboard data."""
    with _scoreboard_lock:
        return _scoreboard_data


def set_cached_scoreboard(data: dict) -> None:
    """Thread-safe setter for cached scoreboard data."""
    global _scoreboard_data
    with _scoreboard_lock:
        _scoreboard_data = data


def poll_loop(season: int, week: int) -> None:
    """Background thread: poll stats and update scoreboard every 45s/10min.

    Game-day heuristic: always 45s during the current week (v1 approximation).
    Outside the current week, poll every 10 min.
    """
    # Load schedule and rosters once at startup.
    schedule = load_json(REPO_ROOT / "state" / "schedule.json", {"regular_season": {}})
    schedule_key = "playoffs" if week >= 15 else "regular_season"
    week_matchups = schedule.get(schedule_key, {}).get(str(week), [])

    # Collect all rostered starters' NFL teams for game-day detection.
    rostered_nfl_teams = set()
    for home_slug, away_slug in week_matchups:
        if not home_slug.startswith("seed_"):
            home_roster = load_json(TEAMS_DIR / home_slug / "roster.json", {})
            for player_id in home_roster.get("starters", {}).values():
                if player_id:
                    players = load_json(REPO_ROOT / "state" / "players.json", {})
                    nfl_team = players.get(player_id, {}).get("team")
                    if nfl_team:
                        rostered_nfl_teams.add(nfl_team)
        if not away_slug.startswith("seed_"):
            away_roster = load_json(TEAMS_DIR / away_slug / "roster.json", {})
            for player_id in away_roster.get("starters", {}).values():
                if player_id:
                    players = load_json(REPO_ROOT / "state" / "players.json", {})
                    nfl_team = players.get(player_id, {}).get("team")
                    if nfl_team:
                        rostered_nfl_teams.add(nfl_team)

    # Main poll loop.
    while not _poll_stop_event.is_set():
        # Load fresh data each iteration.
        stats = fetch_week_stats(season, week)
        rosters_dict = {}
        for team_dir in TEAMS_DIR.iterdir():
            if team_dir.is_dir() and not team_dir.name.startswith("_"):
                roster = load_json(team_dir / "roster.json", {})
                if roster:
                    rosters_dict[team_dir.name] = roster

        players = load_json(REPO_ROOT / "state" / "players.json", {})
        scoring = load_scoring_config()

        # Build and cache the scoreboard.
        scoreboard = build_scoreboard_data(schedule, rosters_dict, stats, players, scoring, week)
        set_cached_scoreboard(scoreboard)

        # Game-day heuristic v1: check if any started starters' NFL teams have begun
        # their game (i.e., have stats). For simplicity, we'll use a 45s poll if
        # any starter has appeared in stats, else 10min (or always 45s during week).
        has_game_started = any(pid in stats for pid in [
            pid for team_roster in rosters_dict.values()
            for pid in team_roster.get("starters", {}).values()
            if pid
        ])

        # For v1: during the current week, always use 45s. Outside, use 10min.
        poll_interval = 45 if has_game_started else 600  # 45s on game day, 10min otherwise

        # Wait with interruption support.
        _poll_stop_event.wait(poll_interval)


class ScoreboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the scoreboard server."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/":
            self.serve_html()
        elif self.path == "/api/scores":
            self.serve_json()
        else:
            self.send_error(404)

    def serve_html(self) -> None:
        """Serve the scoreboard HTML page."""
        scoreboard = get_cached_scoreboard()
        if scoreboard is None:
            scoreboard = {"week": 1, "matchups": []}

        players = load_json(REPO_ROOT / "state" / "players.json", {})
        html = render_html(scoreboard, players)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_json(self) -> None:
        """Serve the scoreboard data as JSON."""
        scoreboard = get_cached_scoreboard()
        if scoreboard is None:
            scoreboard = {"week": 1, "matchups": []}

        json_str = json.dumps(scoreboard, indent=2)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json_str.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress logging to console."""
        pass


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Live fantasy football scoreboard on localhost:PORT"
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Week to display (default: current from standings.json or 1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="NFL season (default: 2026)",
    )
    args = parser.parse_args()

    week = args.week if args.week is not None else load_current_week(args.season)
    season = args.season
    port = args.port

    # Start background poll thread.
    poll_thread = threading.Thread(target=poll_loop, args=(season, week), daemon=True)
    poll_thread.start()

    # Allow a moment for the first poll to complete.
    time.sleep(0.5)

    # Start HTTP server.
    server = ThreadingHTTPServer(("localhost", port), ScoreboardHandler)
    print(f"Scoreboard listening on http://localhost:{port} (week {week}, season {season})")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        _poll_stop_event.set()
        poll_thread.join(timeout=2)
        server.shutdown()
        print("Done.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""build_viewer.py — render web/viewer.html (the interactive league viewer)
from committed league state, for the Sunday refresh loop to publish.

Reuses the tested engine (scoreboard.build_scoreboard_data) for per-matchup
detail and state/standings.json for the standings table. The pure mapping
helpers (viewer_*) are separated from I/O so they can be unit-tested.

Output: web/viewer.html — data injected into web/viewer.template.html at the
`/*__LEAGUE_DATA__*/` marker. The Sunday Routine then publishes that file to
the league's artifact URL.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import scoreboard  # noqa: E402  (reused: build_scoreboard_data, _stat_summary)

TEMPLATE = ROOT / "web" / "viewer.template.html"
OUT = ROOT / "web" / "viewer.html"
WEEKS_DIR = ROOT / "state" / "weeks"


def pretty(slug: str) -> str:
    """Human display name from a team slug (until GM files carry a name)."""
    return str(slug).replace("-", " ").title()


def _load(path: pathlib.Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- pure mappers (unit-tested) --------------------------------------------

def viewer_starters(team: dict, players: dict) -> list:
    """Ordered starter detail for the viewer from a build_scoreboard_data team."""
    starters = team.get("roster", {}).get("starters", {})
    scores = team.get("scores", {})
    stat_lines = team.get("stat_lines", {})
    out = []
    for slot, pid in starters.items():
        if pid is None:
            continue
        info = players.get(pid, {})
        played = pid in stat_lines
        pos = info.get("pos", "?")
        out.append({
            "slot": slot,
            "name": info.get("name", pid),
            "pos": pos,
            "nfl": info.get("team") or "FA",
            "pts": round(scores.get(pid, 0.0), 2),
            "stat": scoreboard._stat_summary(pos, stat_lines.get(pid, {})) if played else "",
            "played": played,
        })
    return out


def viewer_matchup(m: dict, players: dict, recmap: dict) -> dict:
    """Map a build_scoreboard_data matchup to the viewer's shape."""
    def side(t):
        return {
            "slug": t["slug"],
            "name": pretty(t["slug"]),
            "total": round(t["total"], 2),
            "record": recmap.get(t["slug"], "0-0"),
            "starters": viewer_starters(t, players),
        }
    lead = m.get("leader_slug")
    leader = ("home" if lead == m["home_team"]["slug"]
              else "away" if lead == m["away_team"]["slug"] else None)
    return {"home": side(m["home_team"]), "away": side(m["away_team"]), "leader": leader}


def viewer_standings(standings_json: dict) -> list:
    """Map state/standings.json to the viewer's sorted standings list."""
    teams = standings_json.get("teams", {})
    rows = [{
        "slug": s, "name": pretty(s),
        "w": t.get("wins", 0), "l": t.get("losses", 0), "t": t.get("ties", 0),
        "pf": round(t.get("points_for", 0.0), 1),
        "pa": round(t.get("points_against", 0.0), 1),
    } for s, t in teams.items()]
    rows.sort(key=lambda r: (-r["w"], -r["pf"]))  # record, then points-for
    return rows


# --- assembly (reads league state) -----------------------------------------

def _load_scoring():
    raw = _load(ROOT / "config" / "scoring.json", None)
    if raw is None:
        raw = _load(ROOT / "config" / "scoring.default.json", {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _rosters_for_week(season: str, week: int) -> dict:
    """Frozen lineups for a week from lineups.json, else current rosters.

    lineups.json (written by /sunday) is accepted as
    {slug: {"starters": {slot: pid}, ...}} or {slug: {"lineup": {...}}}.
    """
    lp = WEEKS_DIR / f"{season}-w{week:02d}" / "lineups.json"
    data = _load(lp, None)
    if isinstance(data, dict) and data:
        rosters = {}
        for slug, v in data.items():
            starters = v.get("starters") or (v.get("lineup") or {}).get("starters") or {}
            rosters[slug] = {"team": slug, "starters": starters, "bench": [], "ir": []}
        if rosters:
            return rosters
    rosters = {}
    for rp in sorted((ROOT / "teams").glob("*/roster.json")):
        if rp.parent.name.startswith("_"):
            continue
        rosters[rp.parent.name] = _load(rp, {})
    return rosters


def build_league_data(season: str) -> dict:
    players = _load(ROOT / "state" / "players.json", {})
    scoring = _load_scoring()
    schedule = _load(ROOT / "state" / "schedule.json", {"regular_season": {}, "playoffs": {}})
    standings_json = _load(ROOT / "state" / "standings.json", {"teams": {}, "official_weeks": []})
    official = set(standings_json.get("official_weeks", []))

    found_weeks = []
    if WEEKS_DIR.exists():
        for d in sorted(WEEKS_DIR.glob(f"{season}-w*")):
            if (d / "stats.json").exists():
                try:
                    found_weeks.append(int(d.name.split("-w")[1]))
                except ValueError:
                    pass
    found_weeks.sort()

    rec = {}   # running W/L/T for through-week records

    def recstr(slug):
        r = rec.setdefault(slug, {"w": 0, "l": 0, "t": 0})
        return f'{r["w"]}-{r["l"]}' + (f'-{r["t"]}' if r["t"] else "")

    weeks_out = []
    for w in found_weeks:
        is_final = w in official
        stats = _load(WEEKS_DIR / f"{season}-w{w:02d}" / "stats.json", {})
        rosters = _rosters_for_week(season, w)
        board = scoreboard.build_scoreboard_data(schedule, rosters, stats, players, scoring, w)
        matchups = []
        for m in board["matchups"]:
            h, a = m["home_team"]["slug"], m["away_team"]["slug"]
            if is_final:  # fold BEFORE reading record so finals show through-week
                ht, at = m["home_team"]["total"], m["away_team"]["total"]
                if ht > at:
                    rec.setdefault(h, {"w": 0, "l": 0, "t": 0})["w"] += 1
                    rec.setdefault(a, {"w": 0, "l": 0, "t": 0})["l"] += 1
                elif at > ht:
                    rec.setdefault(a, {"w": 0, "l": 0, "t": 0})["w"] += 1
                    rec.setdefault(h, {"w": 0, "l": 0, "t": 0})["l"] += 1
                else:
                    rec.setdefault(h, {"w": 0, "l": 0, "t": 0})["t"] += 1
                    rec.setdefault(a, {"w": 0, "l": 0, "t": 0})["t"] += 1
            matchups.append(viewer_matchup(m, players, {h: recstr(h), a: recstr(a)}))
        weeks_out.append({"week": w, "status": "final" if is_final else "live",
                          "matchups": matchups})

    return {
        "league": "The DuPont Bowl",
        "season": int(season) if str(season).isdigit() else season,
        "weeks": weeks_out,
        "standings": viewer_standings(standings_json),
        "standingsThroughWeek": max(official) if official else 0,
        "updated": datetime.datetime.now().isoformat(),
    }


def render(season: str) -> str:
    league = build_league_data(season)
    template = TEMPLATE.read_text(encoding="utf-8")
    return template.replace("/*__LEAGUE_DATA__*/", json.dumps(league))


def main() -> int:
    ap = argparse.ArgumentParser(description="Render web/viewer.html from league state")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    html = render(a.season)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

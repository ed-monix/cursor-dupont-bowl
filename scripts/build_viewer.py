#!/usr/bin/env python3
"""build_viewer.py — render the interactive league viewer from committed state.

Reuses the tested engine (scoreboard.build_scoreboard_data) for per-matchup
detail and state/standings.json for the standings table. The pure mapping
helpers (viewer_*) are separated from I/O so they can be unit-tested.

Output defaults to web/viewer.html (gitignored). GitHub Pages builds
`--out _site/index.html` from the same template + committed state.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import scoreboard  # noqa: E402  (reused: build_scoreboard_data, _stat_summary)
import forum  # noqa: E402  (reused: read_thread)

TEMPLATE = ROOT / "web" / "viewer.template.html"
OUT = ROOT / "web" / "viewer.html"
WEEKS_DIR = ROOT / "state" / "weeks"


def pretty(slug: str) -> str:
    """Human display name from a team slug (fallback when no franchise name)."""
    return str(slug).replace("-", " ").title()


def team_names() -> dict:
    """{slug: franchise name} for every team whose roster.json carries a
    non-empty "name" (the name that GM chose). Teams without one are omitted,
    so callers fall back to pretty(slug)."""
    out = {}
    for rp in sorted((ROOT / "teams").glob("*/roster.json")):
        if rp.parent.name.startswith("_"):
            continue
        try:
            with open(rp, encoding="utf-8") as f:
                name = (json.load(f).get("name") or "").strip()
        except (json.JSONDecodeError, ValueError, OSError):
            name = ""
        if name:
            out[rp.parent.name] = name
    return out


def _display_name(slug: str, names: Optional[dict]) -> str:
    """Franchise name if the team chose one, else the prettified slug."""
    return (names or {}).get(slug) or pretty(slug)


def gm_names() -> dict:
    """{slug: GM person name} from each team's general-manager.md title line
    '# General Manager: <name>'. Human-slot teams (no GM file) are omitted, so
    callers render no GM subtitle for them."""
    out = {}
    for gp in sorted((ROOT / "teams").glob("*/general-manager.md")):
        if gp.parent.name.startswith("_"):
            continue
        try:
            with open(gp, encoding="utf-8") as f:
                first = f.readline()
        except OSError:
            continue
        m = re.match(r"#\s*General Manager:\s*(.+?)\s*$", first)
        if m:
            out[gp.parent.name] = m.group(1).strip()
    return out


def _load(path: pathlib.Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _section(md_text: str, heading: str) -> str:
    """Extract a markdown section by heading (## format).

    Returns the content under the heading up to (but not including) the next
    heading at the same or higher level. Returns "" if heading not found.
    """
    if not md_text or not heading:
        return ""
    lines = md_text.split("\n")
    section_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## ") and heading in line:
            section_start = i + 1
            break
    if section_start is None:
        return ""

    section_lines = []
    for i in range(section_start, len(lines)):
        if lines[i].startswith("## ") or lines[i].startswith("# "):
            break
        section_lines.append(lines[i])
    return "\n".join(section_lines).strip()


def _frontmatter_description(path: pathlib.Path) -> str:
    """Extract the description: line from YAML frontmatter.

    Frontmatter is between --- markers at the start of a file.
    Returns "" if file doesn't exist or has no description field.
    """
    if not path.exists():
        return ""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return ""

    end_marker = content.find("\n---\n", 4)
    if end_marker == -1:
        return ""

    frontmatter = content[4:end_marker]
    for line in frontmatter.split("\n"):
        if line.startswith("description:"):
            # Extract the value after "description: "
            desc = line[len("description:"):].strip()
            # Remove quotes if present
            if desc.startswith('"') and desc.endswith('"'):
                desc = desc[1:-1]
            elif desc.startswith("'") and desc.endswith("'"):
                desc = desc[1:-1]
            return desc
    return ""


def _load_feed(season: str, week: int, names: Optional[dict] = None) -> dict:
    """Load the week's feed (tabloid, forum, recap).

    Returns {"tabloid": str, "forum": [posts], "recap": str}.
    Each forum post has {timestamp, team, post, name (pretty slug)}.
    Raw strings — no escaping or markdown conversion.
    """
    # Tabloid
    tabloid_path = ROOT / "state" / "news" / f"{season}-w{week:02d}.md"
    tabloid = ""
    if tabloid_path.exists():
        with open(tabloid_path, encoding="utf-8") as f:
            tabloid = f.read()

    # Forum (newest first, with name added)
    forum_posts = forum.read_thread(ROOT, week, season)
    forum_posts_out = []
    for post in reversed(forum_posts):  # reverse to newest first
        post_with_name = dict(post)
        post_with_name["name"] = _display_name(post["team"], names)
        forum_posts_out.append(post_with_name)

    # Recap
    recap_path = ROOT / "state" / "weeks" / f"{season}-w{week:02d}" / "recap.md"
    recap = ""
    if recap_path.exists():
        with open(recap_path, encoding="utf-8") as f:
            recap = f.read()

    return {
        "tabloid": tabloid,
        "forum": forum_posts_out,
        "recap": recap,
    }


def _load_guide(season: str, names: Optional[dict] = None,
                gms: Optional[dict] = None) -> dict:
    """Load the league guide (mission, rules, cast, howItRuns).

    Returns {"mission": str, "rules": str, "cast": [...], "howItRuns": [...]}.
    """
    # Mission: paragraph(s) under ## Mission in README.md (up to next ##)
    readme_path = ROOT / "README.md"
    mission = ""
    if readme_path.exists():
        with open(readme_path, encoding="utf-8") as f:
            readme_text = f.read()
        mission = _section(readme_text, "Mission")

    # Rules: verbatim contents of config/league-rules.md
    rules_path = ROOT / "config" / "league-rules.md"
    rules = ""
    if rules_path.exists():
        with open(rules_path, encoding="utf-8") as f:
            rules = f.read()

    # Cast: one per team + commissioner + media
    standings_json = _load(ROOT / "state" / "standings.json", {"teams": {}})
    teams_standing = standings_json.get("teams", {})

    cast = []

    # AI and human teams
    teams_dir = ROOT / "teams"
    if teams_dir.exists():
        for team_dir in sorted(teams_dir.iterdir()):
            if not team_dir.is_dir() or team_dir.name.startswith("_"):
                continue
            slug = team_dir.name
            # Every team is GM-run; the owners' two are just human-owned.
            kind = "human" if slug in ("your-team", "wifes-team") else "ai"

            # Record from standings
            record = ""
            team_standing = teams_standing.get(slug, {})
            if team_standing:
                w = team_standing.get("wins", 0)
                l = team_standing.get("losses", 0)
                t = team_standing.get("ties", 0)
                record = f"{w}-{l}" + (f"-{t}" if t else "")

            # Bio from Public bio section in general-manager.md
            bio = "Signing in progress"
            gm_path = team_dir / "general-manager.md"
            if gm_path.exists():
                with open(gm_path, encoding="utf-8") as f:
                    gm_text = f.read()
                bio_section = _section(gm_text, "Public bio")
                if bio_section:
                    # Take just the first paragraph (split on double newline or take the first line(s))
                    paras = bio_section.split("\n\n")
                    if paras and paras[0].strip():
                        bio = paras[0].strip()

            cast.append({
                "slug": slug,
                "name": _display_name(slug, names),
                "gm": (gms or {}).get(slug),
                "kind": kind,
                "record": record,
                "bio": bio,
            })

    # Commissioner
    commissioner_path = ROOT / "agents" / "commissioner.md"
    commissioner_bio = "Scrupulously fair, permanently unimpressed."
    if commissioner_path.exists():
        with open(commissioner_path, encoding="utf-8") as f:
            commissioner_text = f.read()
        # Extract first paragraph after the title (up to first blank line or ##)
        lines = commissioner_text.split("\n")
        bio_lines = []
        in_bio = False
        for line in lines:
            if line.startswith("## Jurisdiction"):
                break
            if in_bio:
                if not line.strip():
                    break
                bio_lines.append(line)
            elif line.strip() and not line.startswith("#"):
                in_bio = True
                bio_lines.append(line)
        if bio_lines:
            commissioner_bio = "\n".join(bio_lines).strip()

    cast.append({
        "slug": "commissioner",
        "name": "The Commissioner",
        "kind": "official",
        "record": "",
        "bio": commissioner_bio,
    })

    # Media (Kris Jenner)
    media_path = ROOT / "agents" / "media.md"
    media_bio = "The league's media mogul and tabloid publisher."
    if media_path.exists():
        with open(media_path, encoding="utf-8") as f:
            media_text = f.read()
        # Extract first paragraph after the title (up to first blank line or ##)
        lines = media_text.split("\n")
        bio_lines = []
        in_bio = False
        for line in lines:
            if line.startswith("## "):
                break
            if in_bio:
                if not line.strip():
                    break
                bio_lines.append(line)
            elif line.strip() and not line.startswith("#"):
                in_bio = True
                bio_lines.append(line)
        if bio_lines:
            media_bio = "\n".join(bio_lines).strip()

    cast.append({
        "slug": "media",
        "name": "Kris Jenner",
        "kind": "media",
        "record": "",
        "bio": media_bio,
    })

    # How it runs: descriptions from command frontmatter
    how_it_runs = []
    command_order = ["notes", "waivers", "lineups", "recap", "refresh-board"]
    for cmd in command_order:
        cmd_path = ROOT / ".claude" / "commands" / f"{cmd}.md"
        desc = _frontmatter_description(cmd_path)
        if desc:
            how_it_runs.append({
                "cmd": f"/{cmd}",
                "desc": desc,
            })

    return {
        "mission": mission,
        "rules": rules,
        "cast": cast,
        "howItRuns": how_it_runs,
    }


def load_draft_log(path: pathlib.Path) -> list:
    """Read a draft-log.jsonl into a list of pick dicts (bad lines skipped)."""
    picks = []
    if not path.exists():
        return picks
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                picks.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                pass
    return picks


def draft_from_log(picks: list, names: Optional[dict] = None,
                   gms: Optional[dict] = None) -> dict:
    """Shape a list of draft-log picks into the viewer's draft board:
    {"hasDraft": bool, "rounds": [{"round": int, "picks": [...]}, ...]}, ordered
    by overall pick, grouped by round. Each pick carries the franchise name and
    (when the team has a GM file) the GM's name. Pure."""
    if not picks:
        return {"hasDraft": False, "rounds": []}
    picks = sorted(picks, key=lambda p: p.get("pick_no") or 0)
    rounds: list = []
    by_round: dict = {}
    for p in picks:
        r = p.get("round") or 0
        slug = p.get("team") or p.get("slug")
        bucket = by_round.get(r)
        if bucket is None:
            bucket = {"round": r, "picks": []}
            by_round[r] = bucket
            rounds.append(bucket)
        seq = len(bucket["picks"]) + 1
        bucket["picks"].append({
            "overall": p.get("pick_no"),
            "label": f"{r}.{seq:02d}",
            "slug": slug,
            "team": _display_name(slug, names),
            "gm": (gms or {}).get(slug),
            "player": p.get("name"),
            "pos": p.get("pos"),
            "nfl": p.get("nfl"),
            "commentary": p.get("commentary") or "",
        })
    return {"hasDraft": True, "rounds": rounds}


def _load_draft(season: str, names: Optional[dict] = None,
                gms: Optional[dict] = None) -> dict:
    """Load the real draft board from state/draft-log.jsonl (empty until the
    draft has run). season is accepted for symmetry; the log is season-global."""
    picks = load_draft_log(ROOT / "state" / "draft-log.jsonl")
    return draft_from_log(picks, names, gms)


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


def viewer_matchup(m: dict, players: dict, recmap: dict, names: Optional[dict] = None,
                   gms: Optional[dict] = None) -> dict:
    """Map a build_scoreboard_data matchup to the viewer's shape."""
    def side(t):
        return {
            "slug": t["slug"],
            "name": _display_name(t["slug"], names),
            "gm": (gms or {}).get(t["slug"]),
            "total": round(t["total"], 2),
            "record": recmap.get(t["slug"], "0-0"),
            "starters": viewer_starters(t, players),
        }
    lead = m.get("leader_slug")
    leader = ("home" if lead == m["home_team"]["slug"]
              else "away" if lead == m["away_team"]["slug"] else None)
    return {"home": side(m["home_team"]), "away": side(m["away_team"]), "leader": leader}


def viewer_standings(standings_json: dict, names: Optional[dict] = None,
                     gms: Optional[dict] = None) -> list:
    """Map state/standings.json to the viewer's sorted standings list."""
    teams = standings_json.get("teams", {})
    rows = [{
        "slug": s, "name": _display_name(s, names), "gm": (gms or {}).get(s),
        "w": t.get("wins", 0), "l": t.get("losses", 0), "t": t.get("ties", 0),
        "pf": round(t.get("points_for", 0.0), 1),
        "pa": round(t.get("points_against", 0.0), 1),
    } for s, t in teams.items()]
    rows.sort(key=lambda r: (-r["w"], -r["pf"]))  # record, then points-for
    return rows


_SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "K", "DEF"]


def _slot_index(slot: str) -> int:
    return _SLOT_ORDER.index(slot) if slot in _SLOT_ORDER else len(_SLOT_ORDER)


def viewer_roster(roster: dict, players: dict, names: Optional[dict] = None,
                  gms: Optional[dict] = None) -> dict:
    """Map one team's roster.json (ids only) into the viewer's roster shape,
    resolving every player id to {id, name, pos, nfl}. Pure."""
    slug = roster.get("team")

    def resolve(pid):
        info = players.get(pid, {}) if pid is not None else {}
        return {
            "id": pid,
            "name": info.get("name", pid) if pid is not None else None,
            "pos": info.get("pos", "?") if pid is not None else "",
            "nfl": (info.get("team") or "FA") if pid is not None else "",
        }

    starters = [
        dict(resolve(pid), slot=slot)
        for slot, pid in (roster.get("starters") or {}).items()
    ]
    starters.sort(key=lambda r: _slot_index(r["slot"]))
    bench = [resolve(pid) for pid in (roster.get("bench") or [])]
    ir = [resolve(pid) for pid in (roster.get("ir") or [])]

    return {
        "slug": slug,
        "name": _display_name(slug, names),
        "gm": (gms or {}).get(slug),
        "faabRemaining": roster.get("faab_remaining"),
        "starters": starters,
        "bench": bench,
        "ir": ir,
    }


def _playoff_label(token: str, names: Optional[dict] = None) -> str:
    """Pretty-print a playoffs.json placeholder token ('seed_3', 'winner_15_2')
    until it resolves to a real team slug; real slugs get the franchise name."""
    if token.startswith("seed_"):
        return "Seed " + token.split("_", 1)[1]
    if token.startswith("winner_"):
        parts = token.split("_")
        if len(parts) == 3:
            return f"Winner of Wk{parts[1]} #{parts[2]}"
    return _display_name(token, names)


def viewer_schedule(schedule_json: dict, names: Optional[dict] = None) -> dict:
    """Map state/schedule.json into the viewer's schedule shape: every
    regular-season week's matchups with resolved franchise names, and every
    playoffs week with its (placeholder, pre-seeding) labels. Pure."""
    def week_list(section: dict, label_fn) -> list:
        out = []
        for wk in sorted(section.keys(), key=lambda k: int(k)):
            pairs = section[wk] or []
            out.append({
                "week": int(wk),
                "matchups": [
                    {"home": label_fn(h), "away": label_fn(a)} for h, a in pairs
                ],
            })
        return out

    regular = week_list(schedule_json.get("regular_season", {}) or {},
                        lambda slug: _display_name(slug, names))
    playoffs = week_list(schedule_json.get("playoffs", {}) or {},
                         lambda token: _playoff_label(token, names))
    return {"regularSeason": regular, "playoffs": playoffs}


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
    lp = ROOT / "state" / "weeks" / f"{season}-w{week:02d}" / "lineups.json"
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


def _load_rosters(players: dict, names: Optional[dict] = None,
                  gms: Optional[dict] = None) -> dict:
    """Load every team's current teams/*/roster.json into the viewer's roster
    shape (empty until the draft has run)."""
    teams = []
    for rp in sorted((ROOT / "teams").glob("*/roster.json")):
        if rp.parent.name.startswith("_"):
            continue
        roster = _load(rp, {})
        if not roster:
            continue
        teams.append(viewer_roster(roster, players, names, gms))
    teams.sort(key=lambda t: t["name"])
    return {"hasRosters": bool(teams), "teams": teams}


def build_league_data(season: str) -> dict:
    names = team_names()  # {slug: franchise name}; missing -> pretty(slug)
    gms = gm_names()      # {slug: GM person name}; human slots omitted
    players = _load(ROOT / "state" / "players.json", {})
    scoring = _load_scoring()
    schedule = _load(ROOT / "state" / "schedule.json", {"regular_season": {}, "playoffs": {}})
    standings_json = _load(ROOT / "state" / "standings.json", {"teams": {}, "official_weeks": []})
    official = set(standings_json.get("official_weeks", []))

    # A week belongs in the viewer as soon as there's anything to show for
    # it — stats (scores), or Feed content (tabloid/forum/recap) that exists
    # well before kickoff. Gating on stats.json alone hid the whole week,
    # Feed included, until Monday's /recap — exactly backwards, since the
    # Saturday tabloid and forum are meant to be read before the games.
    found_weeks = []
    weeks_dir = ROOT / "state" / "weeks"
    news_dir = ROOT / "state" / "news"
    forum_dir = ROOT / "state" / "forum"
    if weeks_dir.exists():
        for d in sorted(weeks_dir.glob(f"{season}-w*")):
            try:
                w = int(d.name.split("-w")[1])
            except ValueError:
                continue
            has_stats = (d / "stats.json").exists()
            has_feed = ((news_dir / f"{season}-w{w:02d}.md").exists()
                        or (forum_dir / f"{season}-w{w:02d}.jsonl").exists()
                        or (d / "recap.md").exists())
            if has_stats or has_feed:
                found_weeks.append(w)
    # A week's tabloid/forum can also exist with no state/weeks/<w> dir at
    # all yet (e.g. before any sync has run for that week) — catch those too.
    for d, pattern in ((news_dir, f"{season}-w*.md"), (forum_dir, f"{season}-w*.jsonl")):
        if not d.exists():
            continue
        for f in d.glob(pattern):
            try:
                w = int(f.stem.split("-w")[1])
            except ValueError:
                continue
            if w not in found_weeks:
                found_weeks.append(w)
    found_weeks.sort()

    rec = {}   # running W/L/T for through-week records

    def recstr(slug):
        r = rec.setdefault(slug, {"w": 0, "l": 0, "t": 0})
        return f'{r["w"]}-{r["l"]}' + (f'-{r["t"]}' if r["t"] else "")

    weeks_out = []
    for w in found_weeks:
        is_final = w in official
        stats = _load(ROOT / "state" / "weeks" / f"{season}-w{w:02d}" / "stats.json", {})
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
            matchups.append(viewer_matchup(m, players, {h: recstr(h), a: recstr(a)}, names, gms))

        # Load feed (tabloid, forum, recap)
        feed = _load_feed(season, w, names)

        weeks_out.append({
            "week": w,
            "status": "final" if is_final else "live",
            "matchups": matchups,
            "feed": feed,
        })

    # Load guide (mission, rules, cast, howItRuns)
    guide = _load_guide(season, names, gms)
    draft = _load_draft(season, names, gms)
    rosters = _load_rosters(players, names, gms)
    schedule_view = viewer_schedule(schedule, names)

    office = _load_office()
    return {
        "league": "The DuPont Bowl",
        "season": int(season) if str(season).isdigit() else season,
        "weeks": weeks_out,
        "standings": viewer_standings(standings_json, names, gms),
        "standingsThroughWeek": max(official) if official else 0,
        "guide": guide,
        "draft": draft,
        "rosters": rosters,
        "schedule": schedule_view,
        "office": office,
        "updated": datetime.datetime.now().isoformat(),
    }


def _load_office() -> dict:
    """Public slice of state/ops/latest.json for the top-bar office pill."""
    raw = _load(ROOT / "state" / "ops" / "latest.json", {})
    if not isinstance(raw, dict) or not raw:
        return {}
    return {
        "action": raw.get("action"),
        "today": raw.get("today"),
        "week": raw.get("week"),
        "window": raw.get("window"),
        "reason": raw.get("reason"),
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

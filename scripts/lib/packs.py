"""Build the public + private GM packs (token diet for /waivers and /lineups).

GMs never receive `state/players.json` or another team's `general-manager.md`.
The orchestrator pastes pack JSON (or the rendered prompt) into an inline
subagent with tools disabled. Scripts read the fat files; agents do not.

Public pack (one per week, shared): tabloid, trimmed free agents, compact
league board, NFL games this week, standings slice, forum thread, schedule
matchup list.

Private pack (one per team): that GM file, roster, opinions, owner note,
dossier, own + opponent board slices with injury + game window attached.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

import sys

from lib import nfl_slate

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from gm_dossier import build_dossier  # noqa: E402

# Waiver-wire diet: 693 raw FAs is ~132K; GMs pick from the head of each pos.
FA_PER_POS = 12
FA_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

_WEEK_FILE = "{season}-w{week:02d}"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def team_slugs(root: Path) -> list:
    teams = root / "teams"
    if not teams.is_dir():
        return []
    slugs = []
    for child in sorted(teams.iterdir()):
        if child.name.startswith("_"):
            continue
        if (child / "roster.json").exists() or (child / "general-manager.md").exists():
            slugs.append(child.name)
    return slugs


def trim_free_agents(free_agents: dict, per_pos: int = FA_PER_POS) -> dict:
    """Keep the top `per_pos` free agents at each position by proj_pts.

    Output is still `{id: row}` so claim `add` ids stay stable. Rank is
    (-proj_pts, id) so ties are deterministic.
    """
    buckets = {pos: [] for pos in FA_POSITIONS}
    other = []
    for pid, row in (free_agents or {}).items():
        if not isinstance(row, dict):
            continue
        pos = row.get("pos")
        proj = row.get("proj_pts") or 0
        entry = (float(proj), str(pid), pid, row)
        if pos in buckets:
            buckets[pos].append(entry)
        else:
            other.append(entry)
    trimmed = {}
    for pos in FA_POSITIONS:
        ranked = sorted(buckets[pos], key=lambda e: (-e[0], e[1]))
        for _pts, _sid, pid, row in ranked[:per_pos]:
            trimmed[pid] = row
    return trimmed


def _next_opponent(schedule: dict, slug: str, week: int) -> Optional[str]:
    week_key = str(week)
    pairs = []
    regular = (schedule or {}).get("regular_season") or {}
    playoffs = (schedule or {}).get("playoffs") or {}
    pairs = regular.get(week_key) or playoffs.get(week_key) or []
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        home, away = pair[0], pair[1]
        if home == slug:
            return away
        if away == slug:
            return home
    return None


def _standings_slice(standings: dict, slug: str) -> dict:
    teams = (standings or {}).get("teams") or {}
    mine = teams.get(slug) or {}
    compact = {}
    for other, rec in teams.items():
        compact[other] = {
            "wins": rec.get("wins"),
            "losses": rec.get("losses"),
            "ties": rec.get("ties"),
            "points_for": rec.get("points_for"),
        }
    return {"season": standings.get("season"), "me": mine, "league": compact}


def _annotate_side(side: dict, by_team: dict) -> dict:
    """Copy a league-board team blob, attaching game/window/injury on each player."""
    out = {
        "faab_remaining": side.get("faab_remaining"),
        "starters": {},
        "bench": [],
        "ir": [],
    }
    for slot, player in (side.get("starters") or {}).items():
        if player is None:
            out["starters"][slot] = None
        else:
            out["starters"][slot] = nfl_slate.annotate_player_game(player, by_team)
    for player in side.get("bench") or []:
        out["bench"].append(nfl_slate.annotate_player_game(player, by_team))
    for player in side.get("ir") or []:
        out["ir"].append(nfl_slate.annotate_player_game(player, by_team))
    return out


def load_week_games(root: Path, week: int, season: str = "2026") -> list:
    week_path = root / "state" / "weeks" / _WEEK_FILE.format(season=season, week=week) / "nfl-games.json"
    games = _read_json(week_path, None)
    if games:
        return games
    season_sched = _read_json(root / "state" / "nfl-schedule.json", [])
    return nfl_slate.games_for_week(season_sched, week)


def build_public_pack(root: Union[str, Path], week: int, season: str = "2026") -> dict:
    root = Path(root)
    label = _WEEK_FILE.format(season=season, week=week)
    fa = _read_json(root / "state" / "free-agents.json", {})
    board = _read_json(root / "state" / "league-board.json", {})
    standings = _read_json(root / "state" / "standings.json", {})
    schedule = _read_json(root / "state" / "schedule.json", {})
    games = load_week_games(root, week, season)
    tabloid = _read_text(root / "state" / "news" / f"{label}.md")
    forum = []
    forum_path = root / "state" / "forum" / f"{label}.jsonl"
    if forum_path.exists():
        for line in forum_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                forum.append(json.loads(line))
            except ValueError:
                continue
    prev = week - 1
    last_forum = []
    if prev >= 1:
        prev_label = _WEEK_FILE.format(season=season, week=prev)
        prev_path = root / "state" / "forum" / f"{prev_label}.jsonl"
        if prev_path.exists():
            for line in prev_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        last_forum.append(json.loads(line))
                    except ValueError:
                        pass

    trimmed_fa = trim_free_agents(fa)
    compact_board = {}
    for slug, side in (board or {}).items():
        compact_board[slug] = {
            "faab_remaining": side.get("faab_remaining"),
            "starters": {
                slot: (
                    None if p is None else {
                        "id": p.get("id"), "name": p.get("name"), "pos": p.get("pos"),
                        "nfl": p.get("nfl"), "proj_pts": p.get("proj_pts"),
                        "status": p.get("status"), "injury": p.get("injury"),
                    }
                )
                for slot, p in (side.get("starters") or {}).items()
            },
            "bench": [
                {
                    "id": p.get("id"), "name": p.get("name"), "pos": p.get("pos"),
                    "nfl": p.get("nfl"), "proj_pts": p.get("proj_pts"),
                    "status": p.get("status"), "injury": p.get("injury"),
                }
                for p in (side.get("bench") or [])
            ],
        }

    return {
        "season": season,
        "week": week,
        "tabloid": tabloid,
        "forum": forum,
        "last_week_forum": last_forum,
        "free_agents_trimmed": trimmed_fa,
        "free_agents_trimmed_count": len(trimmed_fa),
        "free_agents_full_count": len(fa) if isinstance(fa, dict) else 0,
        "league_board": compact_board,
        "nfl_games": nfl_slate.compact_week_games(games),
        "standings": {
            "season": standings.get("season"),
            "official_weeks": standings.get("official_weeks"),
            "teams": {
                slug: {
                    "wins": rec.get("wins"),
                    "losses": rec.get("losses"),
                    "ties": rec.get("ties"),
                    "points_for": rec.get("points_for"),
                }
                for slug, rec in ((standings.get("teams") or {}).items())
            },
        },
        "fantasy_matchups": (
            ((schedule.get("regular_season") or {}).get(str(week)))
            or ((schedule.get("playoffs") or {}).get(str(week)))
            or []
        ),
        "rules": {
            "do_not_read": [
                "state/players.json",
                "state/weeks/*/projections.json",
                "state/news/buzz/",
                "teams/*/general-manager.md (other than yours)",
                "teams/*/opinions.json (other than yours)",
            ],
            "proj_pts_are_an_opinion": True,
            "tools": "none — everything you need is in this pack",
        },
    }


def build_private_pack(
    root: Union[str, Path],
    slug: str,
    week: int,
    season: str = "2026",
    public: Optional[dict] = None,
    run: str = "waivers",
    window: Optional[str] = None,
) -> dict:
    """THIS TEAM's private context + a pointer to the public pack fields.

    Never opens `teams/<other>/`.
    """
    root = Path(root)
    if slug.startswith("_"):
        raise ValueError(f"invalid team slug {slug!r}")
    team_dir = root / "teams" / slug
    if not team_dir.is_dir():
        raise FileNotFoundError(f"no team folder {team_dir}")

    public = public if public is not None else build_public_pack(root, week, season)
    roster = _read_json(team_dir / "roster.json", {})
    opinions = _read_json(team_dir / "opinions.json", {})
    gm_text = _read_text(team_dir / "general-manager.md")
    label = _WEEK_FILE.format(season=season, week=week)
    note = _read_text(team_dir / "notes" / f"{label}.md")
    dossier = build_dossier(root, slug, season=season, current_week=week)

    games = load_week_games(root, week, season)
    by_team = nfl_slate.index_games_by_team(games)
    board = public.get("league_board") or {}
    # Re-load full board for annotation (compact board dropped ir; annotate from file)
    full_board = _read_json(root / "state" / "league-board.json", {})
    mine = _annotate_side(full_board.get(slug) or board.get(slug) or {}, by_team)
    opponent = _next_opponent(_read_json(root / "state" / "schedule.json", {}), slug, week)
    opp_side = None
    if opponent:
        opp_side = _annotate_side(full_board.get(opponent) or board.get(opponent) or {}, by_team)

    locked = {}
    lineups = _read_json(
        root / "state" / "weeks" / label / "lineups.json", {})
    if isinstance(lineups, dict):
        locked = (lineups.get(slug) or {}).get("locked_slots") or {}

    return {
        "run": run,
        "window": window,
        "team": slug,
        "opponent": opponent,
        "general_manager_md": gm_text,
        "roster": roster,
        "opinions": opinions,
        "owner_note": note,
        "dossier": dossier,
        "my_board": mine,
        "opponent_board": opp_side,
        "locked_slots": locked,
        "public": {
            "tabloid": public.get("tabloid"),
            "forum": public.get("forum"),
            "last_week_forum": public.get("last_week_forum"),
            "free_agents_trimmed": public.get("free_agents_trimmed") if run == "waivers" else None,
            "nfl_games": public.get("nfl_games"),
            "standings": public.get("standings"),
            "fantasy_matchups": public.get("fantasy_matchups"),
            "rules": public.get("rules"),
            # Full league board only on the waiver/trade run for scouting.
            "league_board": public.get("league_board") if run == "waivers" else None,
        },
    }


def render_gm_prompt(pack: dict) -> str:
    """Inline prompt body: isolation + pack JSON. Subagent must not use tools."""
    run = pack.get("run") or "waivers"
    slug = pack.get("team")
    window = pack.get("window")
    schema = (
        "docs/schemas/saturday-decision.json"
        if run == "waivers"
        else "docs/schemas/sunday-lineup.json"
    )
    lines = [
        f"You are the GM of `{slug}` only.",
        "Everything you need is in the JSON pack below. Do NOT read files, run commands, or use tools.",
        "Do NOT open state/players.json, projections, buzz/, or any other team's general-manager.md or opinions.json.",
        f"Reply with ONE JSON object matching {schema} (plus in-character fields the schema allows).",
        "proj_pts is the analytics department's opinion — trust, discount, or resent it per your GM file.",
        "Beliefs first: state your in-character read, then choose moves consistent with that read.",
    ]
    if run == "lineups" and window:
        lines.append(
            f"This is lineup window `{window}`. Do not move players in locked_slots. "
            "Early window: lock Tue–Sat NFL games. Main window: remaining Sun/Mon (and anyone still unlocked)."
        )
    lines.append("")
    lines.append("```json")
    # Drop the raw GM file duplication? It's inside the pack as general_manager_md.
    lines.append(json.dumps(pack, indent=1, sort_keys=False))
    lines.append("```")
    return "\n".join(lines)


def pack_sizes(public: dict, private: dict) -> dict:
    """Byte sizes for the efficiency log — not for agents."""
    pub = json.dumps(public).encode("utf-8")
    priv = json.dumps(private).encode("utf-8")
    prompt = render_gm_prompt(private).encode("utf-8")
    return {
        "public_bytes": len(pub),
        "private_bytes": len(priv),
        "prompt_bytes": len(prompt),
        "fa_trimmed": public.get("free_agents_trimmed_count"),
        "fa_full": public.get("free_agents_full_count"),
    }

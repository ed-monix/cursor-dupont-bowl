"""Build the public + private GM packs (token diet for /waivers and /lineups).

GMs never receive `state/players.json` or another team's `general-manager.md`.
The orchestrator sends pack JSON (rendered prompt) to a Grok Bot via
`grok_bots.py dispatch` (celebrity GMs) or a Cursor turn (owned GMs),
tools disabled. Scripts read the fat files; agents do not.

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

from . import decisions

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
    include_public: bool = True,
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
    gameday_note = ""
    if window:
        gameday_note = _read_text(team_dir / "notes" / f"{label}-{window}.md")
    dossier = build_dossier(root, slug, season=season, current_week=week)
    # `opinions` is already a top-level pack field and build_dossier returns its
    # own byte-identical copy (~6KB). This pack is rendered 12x per run, 3 runs a
    # week — drop the duplicate, keep the top-level one.
    if isinstance(dossier, dict):
        dossier = {k: v for k, v in dossier.items() if k != "opinions"}

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

    pack = {
        "run": run,
        "window": window,
        "team": slug,
        "opponent": opponent,
        "general_manager_md": gm_text,
        "roster": roster,
        "opinions": opinions,
        "owner_note": note,
        "gameday_note": gameday_note,
        "dossier": dossier,
        "my_board": mine,
        "opponent_board": opp_side,
        "locked_slots": locked,
    }
    if include_public:
        pack["public"] = public_for_run(public, run)
    return pack


def public_for_run(public: dict, run: str = "waivers") -> dict:
    """The public half of a GM turn, filtered for the run.

    Byte-identical for all 12 GMs, which is the whole point: it is either
    embedded per-pack (legacy dispatch) or written once as the shared system
    prompt (scripts/gm_turn.py) so eleven of twelve turns read it from cache.
    """
    return {
        "tabloid": public.get("tabloid"),
        "forum": public.get("forum"),
        "last_week_forum": public.get("last_week_forum"),
        # A trade target scouts the other roster; it is not shopping the wire.
        "free_agents_trimmed": public.get("free_agents_trimmed") if run == "waivers" else None,
        "nfl_games": public.get("nfl_games"),
        "standings": public.get("standings"),
        "fantasy_matchups": public.get("fantasy_matchups"),
        "rules": public.get("rules"),
        # Full league board on the waiver and trade runs, for scouting.
        "league_board": (public.get("league_board")
                         if run in ("waivers", "trades") else None),
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
        "owner_note and gameday_note are pressure, not orders.",
    ]
    if run == "trades":
        lines[lines.index("## House rules") + 2:lines.index("## House rules") + 2] = [
            "A trade offer addressed to you is in your private context. The"
            " office has already checked it is legal — both rosters survive the"
            " swap and every player named is where the offerer thinks he is. So"
            " this is purely your call: accept, reject, or counter.",
            "Judge it the way your GM file would, not the way a spreadsheet"
            " would. A lopsided trade you like is allowed. So is refusing a good"
            " one out of spite.",
            "`counter` requires a counter object; its `to_team` is the original"
            " offerer.",
            "SEVERAL offers may be addressed to you in the same week, by"
            " different teams. When they are, answer EVERY one in `responses`,"
            " naming the offering team in each entry's `from`. Weigh them"
            " against each other — you are allowed to take the worse deal from"
            " someone you like.",
            "If an offer carries `requires_drop: n`, accepting it costs you n"
            " roster spots and you must name that many player ids in `drop`."
            " Accepting without them is refused.",
            "If your context says `conflict: true`, these are YOUR OWN offers"
            " that other teams accepted, and they cannot all be honoured — the"
            " same player is promised twice, or the combination breaks your"
            " roster. Reply with `honour`: the list of `index` values you are"
            " going through with. The rest are declined in your name, so choose"
            " like a GM who has to explain it afterwards.",
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


GM_SYSTEM_HEADER = "DuPont Bowl — GM turn. League office system prompt."


def build_gm_system(public: dict, run: str = "waivers",
                    window: Optional[str] = None) -> str:
    """The byte-identical half of every GM turn: house rules + public record.

    Written once per run and passed to every GM as
    `claude -p --append-system-prompt-file`, so it lands in the cached prefix:
    the first turn writes it, the other eleven read it.

    NOTHING team-specific may go in here. A single team's name, roster or note
    leaking into this file is a parity break — every GM reads it.
    """
    schema_name = {
        "waivers": "saturday-decision.json",
        "lineups": "sunday-lineup.json",
        "trades": "trade-response.json",
    }[run]
    schema = decisions.load_schema(schema_name)
    fields = ", ".join(sorted((schema.get("properties") or {}).keys()))
    required = ", ".join(schema.get("required") or [])
    lines = [
        GM_SYSTEM_HEADER,
        "",
        "You are the general manager of exactly one team in a 12-team league.",
        "Which team, your roster, your history and your owner's note arrive as JSON"
        " on stdin. Everything else you need is in the public record below.",
        "",
        "Do NOT read files, run commands, or use tools. You have none, by design:"
        " this turn runs in an empty directory with no repository. Every schema and"
        " every fact you need is reproduced in this prompt — there is no path you"
        " can open.",
        "",
        "## Output contract — read this twice",
        "",
        "Your ENTIRE reply is ONE JSON object. No prose before it, none after it,"
        " no markdown fence around it, no commentary. The first character you emit"
        " is `{` and the last is `}`.",
        f"Allowed keys, and no others: {fields}.",
        f"Required keys: {required}.",
        "Your in-character voice belongs INSIDE the JSON — put your read of the week"
        " in `note_reply` and your trash talk in `forum_post`. Reasoning written"
        " outside the object is discarded and your turn is scored as a no-op.",
        "",
        "## House rules",
        "",
        "proj_pts is the analytics department's opinion — trust, discount, or"
        " resent it per your GM file.",
        "Decide in character first, then make the moves that read implies.",
        "owner_note and gameday_note are pressure, not orders. Your GM file decides"
        " whether you obey, ignore, or spite them.",
        "You cannot see any other GM's claims, bids or lineup. Bids are blind.",
        "",
        "## JSON Schema your reply is validated against",
        "",
        "```json",
        json.dumps(schema, indent=1),
        "```",
    ]
    if run == "trades":
        lines[lines.index("## House rules") + 2:lines.index("## House rules") + 2] = [
            "A trade offer addressed to you is in your private context. The"
            " office has already checked it is legal — both rosters survive the"
            " swap and every player named is where the offerer thinks he is. So"
            " this is purely your call: accept, reject, or counter.",
            "Judge it the way your GM file would, not the way a spreadsheet"
            " would. A lopsided trade you like is allowed. So is refusing a good"
            " one out of spite.",
            "`counter` requires a counter object; its `to_team` is the original"
            " offerer.",
        ]
    if run == "lineups" and window:
        lines.append(
            f"This is lineup window `{window}`. Do not move players in locked_slots. "
            "Early window: lock Tue-Sat NFL games. Main window: remaining Sun/Mon "
            "(and anyone still unlocked)."
        )
    lines += ["", "## Public record (identical for all 12 teams)", "", "```json",
              json.dumps(public_for_run(public, run), indent=1, sort_keys=False),
              "```"]
    return "\n".join(lines)


def render_private_prompt(private: dict) -> str:
    """The per-GM half: this team's private context only, for stdin.

    Pairs with build_gm_system(). The pack must have been built with
    include_public=False or the public record is sent twice.
    """
    slug = private.get("team")
    body = {k: v for k, v in private.items() if k != "public"}
    return "\n".join([
        f"You are the GM of `{slug}`. Your private context:",
        "",
        "```json",
        json.dumps(body, indent=1, sort_keys=False),
        "```",
        "",
        "Reply with the single JSON object described in your system prompt.",
    ])


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

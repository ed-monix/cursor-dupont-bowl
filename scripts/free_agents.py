#!/usr/bin/env python3
"""free_agents.py — derive the weekly free-agent pool (PLAN.md §8).

state/free-agents.json is a DERIVED file: every player in state/players.json
that is not on any team's roster, with this week's projected points attached.
The Saturday roster run (/saturday) feeds it to each GM as the waiver-wire board.

Data contract (PLAN.md §8):
    state/free-agents.json = {player_id: {name, pos, team, status, injury, proj_pts,
                                          proj: {raw_keys...}, last_wk_pts}, ...}

Pure logic (`derive_free_agents`) is separated from I/O so it is unit-testable
with in-memory fixtures; the CLI just loads the repo's files and writes the pool.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.scoring import score_player  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Position-specific projection keys whitelists (raw projection keys that matter for evaluation).
PROJ_KEYS_BY_POSITION = {
    "QB": {"pass_yd", "pass_td", "pass_int", "rush_yd"},
    "RB": {"rush_yd", "rush_td", "rec", "rec_yd"},
    "WR": {"rec", "rec_yd", "rec_td"},
    "TE": {"rec", "rec_yd", "rec_td"},
    "K": {"fgm", "fga", "xpm"},
    "DEF": {"pts_allow", "sack", "int"},
}


def rostered_player_ids(rosters) -> set:
    """All player_ids currently on any roster (starters + bench + ir).

    `rosters` may be a dict {slug: roster} or any iterable of roster dicts.
    """
    if isinstance(rosters, dict):
        rosters = rosters.values()
    ids: set = set()
    for roster in rosters:
        for pid in (roster.get("starters") or {}).values():
            if pid is not None:
                ids.add(pid)
        for pid in roster.get("bench", []) or []:
            ids.add(pid)
        for pid in roster.get("ir", []) or []:
            ids.add(pid)
    return ids


def derive_free_agents(players: dict, rosters, projections: dict, scoring: dict,
                       prior_stats: dict | None = None) -> dict:
    """Return {player_id: {name, pos, team, status, injury, proj_pts, proj, last_wk_pts}}
    for every player in `players` not on any roster, with projected points from
    `projections` scored through `scoring` (a player with no projection scores 0.0).

    status and injury are pulled from the player's players.json entry.
    proj is a dict of raw projection keys filtered to a per-position whitelist
        (only keys present in the projection row are included, so it stays sparse).
    last_wk_pts is the player's actual points from prior week's stats when prior_stats
        is provided; None otherwise.

    Pure."""
    rostered = rostered_player_ids(rosters)
    free_agents = {}
    for pid, info in players.items():
        if pid in rostered:
            continue
        pos = info.get("pos")
        proj_row = projections.get(pid, {}) or {}

        # Build the proj dict with only whitelisted keys present in the row.
        proj_keys = PROJ_KEYS_BY_POSITION.get(pos, set())
        proj_dict = {k: proj_row[k] for k in proj_keys if k in proj_row}

        # Compute last_wk_pts if prior_stats is provided.
        last_wk_pts = None
        if prior_stats is not None and pid in prior_stats:
            last_wk_pts = round(score_player(prior_stats[pid], scoring), 2)

        free_agents[pid] = {
            "name": info.get("name"),
            "pos": pos,
            "team": info.get("team"),
            "status": info.get("status"),
            "injury": info.get("injury"),
            "proj_pts": round(score_player(proj_row, scoring), 2),
            "proj": proj_dict,
            "last_wk_pts": last_wk_pts,
        }
    return free_agents


def _load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_rosters(rosters_dir: pathlib.Path) -> dict:
    rosters = {}
    for roster_path in sorted(rosters_dir.glob("*/roster.json")):
        if roster_path.parent.name.startswith("_"):
            continue
        with open(roster_path, encoding="utf-8") as f:
            rosters[roster_path.parent.name] = json.load(f)
    return rosters


def _load_scoring(config_dir: pathlib.Path) -> dict:
    path = config_dir / "scoring.json"
    if not path.exists():
        path = config_dir / "scoring.default.json"
    raw = _load_json(path, {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive state/free-agents.json for a week")
    ap.add_argument("--week", type=int, required=True, help="week number (for projections)")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default=str(ROOT / "state" / "free-agents.json"))
    a = ap.parse_args()

    players = _load_json(ROOT / "state" / "players.json", {})
    if not players:
        sys.exit("state/players.json missing or empty — run sync_sleeper.py --players first")
    rosters = _load_rosters(ROOT / "teams")
    projections = _load_json(
        ROOT / "state" / "weeks" / f"{a.season}-w{a.week:02d}" / "projections.json", {})
    scoring = _load_scoring(ROOT / "config")

    # Load prior week's stats if it exists (for last_wk_pts).
    prior_stats = None
    if a.week > 1:
        prior_stats = _load_json(
            ROOT / "state" / "weeks" / f"{a.season}-w{(a.week - 1):02d}" / "stats.json", None)

    free_agents = derive_free_agents(players, rosters, projections, scoring, prior_stats)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(free_agents, indent=1))
    print(f"wrote {out} ({len(free_agents)} free agents; {len(players) - len(free_agents)} rostered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""league_board.py — derive the public league roster board (PLAN.md §8).

state/league-board.json is a DERIVED file: all 12 teams' rosters resolved
with players and projections, so a GM can scout trade targets and name real
players in trade offers. Rosters and FAAB are public record (only GM *files*
are secret), so this breaks no isolation.

Data contract (PLAN.md §8):
    state/league-board.json = {
        slug: {
            starters: {slot: {id, name, pos, nfl, proj_pts} | null},
            bench: [{id, name, pos, nfl, proj_pts}, ...],
            ir: [{id, name, pos, nfl, proj_pts}, ...],
            faab_remaining: int
        },
        ...
    }

Pure logic (`derive_league_board`) is separated from I/O so it is unit-testable
with in-memory fixtures; the CLI just loads the repo's files and writes the board.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.scoring import score_player  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def resolve_player(player_id: str | None, players: dict, projections: dict, scoring: dict) -> dict | None:
    """Resolve a player_id to {id, name, pos, nfl, proj_pts}.

    If player_id is None, returns None.
    If player_id is in players, resolves from there with proj_pts computed.
    If player_id is missing from players, returns {id, name:id, pos:"?", nfl:"FA", proj_pts: 0}.
    """
    if player_id is None:
        return None

    if player_id in players:
        info = players[player_id]
        proj = projections.get(player_id, {}) or {}
        return {
            "id": player_id,
            "name": info.get("name"),
            "pos": info.get("pos"),
            "nfl": info.get("team"),
            "proj_pts": round(score_player(proj, scoring), 2),
        }
    else:
        # Player missing from players.json; resolve with defaults
        proj = projections.get(player_id, {}) or {}
        return {
            "id": player_id,
            "name": player_id,
            "pos": "?",
            "nfl": "FA",
            "proj_pts": round(score_player(proj, scoring), 2),
        }


def derive_league_board(rosters: dict, players: dict, projections: dict, scoring: dict) -> dict:
    """Return {slug: {starters, bench, ir, faab_remaining}} for all teams.

    `rosters` = {slug: roster_json} where roster_json is
    {team, faab_remaining, starters:{slot:pid|null}, bench:[pid], ir:[pid]}.

    Starters are a dict keyed by slot; each non-null value is a resolved player.
    Bench and ir are lists of resolved players (each item a dict with id/name/pos/nfl/proj_pts).
    A null starter slot stays null.
    """
    board = {}
    for slug, roster in rosters.items():
        starters = {}
        for slot, player_id in (roster.get("starters") or {}).items():
            starters[slot] = resolve_player(player_id, players, projections, scoring)

        bench = []
        for player_id in roster.get("bench", []) or []:
            resolved = resolve_player(player_id, players, projections, scoring)
            if resolved is not None:
                bench.append(resolved)

        ir = []
        for player_id in roster.get("ir", []) or []:
            resolved = resolve_player(player_id, players, projections, scoring)
            if resolved is not None:
                ir.append(resolved)

        board[slug] = {
            "starters": starters,
            "bench": bench,
            "ir": ir,
            "faab_remaining": roster.get("faab_remaining", 0),
        }

    return board


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
    ap = argparse.ArgumentParser(description="Derive state/league-board.json for a week")
    ap.add_argument("--week", type=int, required=True, help="week number (for projections)")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default=str(ROOT / "state" / "league-board.json"))
    a = ap.parse_args()

    players = _load_json(ROOT / "state" / "players.json", {})
    if not players:
        sys.exit("state/players.json missing or empty — run sync_sleeper.py --players first")
    rosters = _load_rosters(ROOT / "teams")
    if not rosters:
        sys.exit("no rosters found in teams/*/roster.json")
    projections = _load_json(
        ROOT / "state" / "weeks" / f"{a.season}-w{a.week:02d}" / "projections.json", {})
    scoring = _load_scoring(ROOT / "config")

    board = derive_league_board(rosters, players, projections, scoring)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=1))
    print(f"wrote {out} ({len(board)} teams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

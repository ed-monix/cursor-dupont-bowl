#!/usr/bin/env python3
"""lineups.py — apply one NFL lineup window (scripts decide freeze/fallback).

    python scripts/lineups.py --week 1 --window early \\
        --decisions state/weeks/2026-w01/canned/lineups-early.json

    python scripts/lineups.py --week 1 --window main --dry-run \\
        --decisions-dir state/weeks/2026-w01/decisions

Reads GM JSON (schema sunday-lineup.json). Writes ``lineups.json`` and
updates ``teams/*/roster.json`` starters. ``--dry-run`` writes only
``lineups-<window>-report.json``.

Does not spawn GMs. Does not write to Sleeper.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import score_week  # noqa: E402
from lib.apply_lineups import apply_lineup_window  # noqa: E402
from lib.rosters import save_roster  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_json(path: pathlib.Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def _load_rosters(teams_dir: pathlib.Path) -> dict:
    rosters = {}
    for roster_path in sorted(teams_dir.glob("*/roster.json")):
        slug = roster_path.parent.name
        if slug.startswith("_"):
            continue
        rosters[slug] = _load_json(roster_path)
    return rosters


def load_decisions(path: pathlib.Path | None, decisions_dir: pathlib.Path | None,
                   window: str) -> dict:
    if path:
        data = _load_json(path)
        if not isinstance(data, dict):
            raise ValueError("decisions file must be a JSON object keyed by team slug")
        return data
    if not decisions_dir:
        raise ValueError("pass --decisions or --decisions-dir")
    out = {}
    for slug_path in sorted(decisions_dir.glob(f"*.lineup-{window}.json")):
        slug = slug_path.name.split(".")[0]
        out[slug] = _load_json(slug_path)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply one /lineups window (no agents).")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--window", choices=("early", "main"), required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--decisions", help="JSON object {slug: {starters, justification}}")
    ap.add_argument("--decisions-dir", help="dir of <slug>.lineup-<window>.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    week_dir = root / "state" / "weeks" / f"{args.season}-w{args.week:02d}"
    teams_dir = root / "teams"
    players = _load_json(root / "state" / "players.json")
    projections = _load_json(week_dir / "projections.json", {})
    scoring = score_week.load_scoring(root / "config")
    games = _load_json(week_dir / "nfl-games.json", [])
    board = _load_json(root / "state" / "league-board.json", {})
    existing = _load_json(week_dir / "lineups.json", {})
    if not isinstance(existing, dict):
        existing = {}
    rosters = _load_rosters(teams_dir)
    decisions = load_decisions(
        pathlib.Path(args.decisions) if args.decisions else None,
        pathlib.Path(args.decisions_dir) if args.decisions_dir else None,
        args.window,
    )

    result = apply_lineup_window(
        rosters, players, projections, scoring, decisions, args.window, games,
        existing_lineups=existing, board=board,
    )
    report_path = week_dir / f"lineups-{args.window}-report.json"
    _write_json(report_path, result["report"])
    if args.dry_run:
        print(json.dumps(result["report"], indent=2))
        return 0

    _write_json(week_dir / "lineups.json", result["lineups"])
    for slug, roster in result["rosters"].items():
        save_roster(roster, teams_dir / slug / "roster.json")
    print(json.dumps(result["report"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

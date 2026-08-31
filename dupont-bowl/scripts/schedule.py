#!/usr/bin/env python3
"""schedule.py — generate state/schedule.json (TASKS.md 2.3, PLAN.md §2/§8).

The pure schedule-generation logic lives in `scripts/lib/schedule_gen.py`
(`generate(team_order, seed=None)`) so it's importable from tests and from
other scripts without going through a CLI or touching disk. This file is
just the CLI: parse team slugs, call `generate()`, write the result.

Usage:
    python scripts/schedule.py TEAM1 TEAM2 ... TEAM12
    python scripts/schedule.py --teams-file teams.json
    python scripts/schedule.py TEAM1 ... TEAM12 --seed 20260830
    python scripts/schedule.py --out state/schedule.json TEAM1 ... TEAM12

Team order: pass exactly 12 unique team slugs, either as positional
arguments or one-per-line/as a JSON list via --teams-file. If neither is
given, defaults to discovering slugs from `teams/*/` (every subdirectory of
teams/ except `_template`) sorted alphabetically -- this only works once all
12 team folders exist (e.g. after the draft has created them); until then,
pass team slugs explicitly.

--seed: optional value forwarded to `generate()` to shuffle the team order
before pairing (see schedule_gen.py docstring) -- e.g. for a draft-day
randomized order. Omit for a deterministic schedule from the team order as
given.

Writes state/schedule.json (pretty-printed, sorted keys) by default; --out
overrides the path.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from schedule_gen import generate  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "state" / "schedule.json"
DEFAULT_TEAMS_DIR = ROOT / "teams"


def discover_team_slugs(teams_dir: pathlib.Path = DEFAULT_TEAMS_DIR) -> list[str]:
    """Sorted list of team-folder names under teams/, excluding _template."""
    if not teams_dir.is_dir():
        return []
    return sorted(
        p.name for p in teams_dir.iterdir() if p.is_dir() and not p.name.startswith("_")
    )


def load_teams_file(path: pathlib.Path) -> list[str]:
    """Read team slugs from a file: JSON list, or one slug per line."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if stripped.startswith("["):
        return json.loads(stripped)
    return [line.strip() for line in text.splitlines() if line.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("teams", nargs="*", help="12 team slugs, in seating order for the round-robin circle")
    ap.add_argument("--teams-file", type=pathlib.Path, help="JSON list or newline-delimited file of 12 team slugs")
    ap.add_argument("--seed", help="optional seed to shuffle team order before pairing (int or string)")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT, help=f"output path (default {DEFAULT_OUT})")
    args = ap.parse_args(argv)

    if args.teams_file:
        team_order = load_teams_file(args.teams_file)
    elif args.teams:
        team_order = args.teams
    else:
        team_order = discover_team_slugs()
        if not team_order:
            ap.error(
                "no team slugs given and none discoverable under teams/ "
                "(pass them positionally or via --teams-file)"
            )

    seed = args.seed
    if seed is not None:
        try:
            seed = int(seed)
        except ValueError:
            pass  # random.Random() also accepts a raw string seed

    try:
        schedule = generate(team_order, seed=seed)
    except ValueError as e:
        ap.error(str(e))
        return 2  # pragma: no cover - ap.error() already exits

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {args.out} ({len(team_order)} teams, seed={seed!r})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

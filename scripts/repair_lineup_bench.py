#!/usr/bin/env python3
"""One-time repair for rosters corrupted by the starters-only lineup apply.

`week 01: apply lineups-main` (b116c05) wrote `starters` and left `bench`
untouched, so every team that changed its lineup ended up holding a promoted
player twice and a demoted player not at all. Five of twelve teams were hit.
The duplicates are visible in the file; the dropped players are not, so the
held set has to come from the commit before the corrupting one.

The repair is the lineup apply as it should have run: take what the team held
before (starters + bench), subtract whoever is starting now, and that is the
bench. Same `reconciled_bench` the fixed apply path uses -- this script picks
the inputs, it does not re-decide anything.

    python scripts/repair_lineup_bench.py --before b116c05^ --dry-run
    python scripts/repair_lineup_bench.py --before b116c05^
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.apply_lineups import reconciled_bench  # noqa: E402
from lib.rosters import validate_roster  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _roster_at(commit: str, slug: str) -> dict:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:teams/{slug}/roster.json"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"cannot read {slug} at {commit}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def duplicates(roster: dict) -> list:
    bench = {str(p) for p in (roster.get("bench") or [])}
    return sorted(
        (slot, str(pid))
        for slot, pid in (roster.get("starters") or {}).items()
        if str(pid) in bench
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--before", required=True,
                    help="commit holding the pre-corruption rosters")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    players = json.loads((ROOT / "state" / "players.json").read_text())
    config = json.loads((ROOT / "config" / "roster.json").read_text())

    repaired = []
    for path in sorted((ROOT / "teams").glob("*/roster.json")):
        slug = path.parent.name
        if slug.startswith("_"):
            continue
        current = json.loads(path.read_text())
        dupes = duplicates(current)
        if not dupes:
            continue

        before = _roster_at(args.before, slug)
        fixed = dict(current)
        fixed["bench"] = reconciled_bench(before, current.get("starters") or {})

        ok, errors = validate_roster(fixed, players, config)
        if not ok:
            raise SystemExit(f"{slug}: repair does not validate: {errors}")

        held_before = set(str(p) for p in (before.get("bench") or [])) | {
            str(p) for p in (before.get("starters") or {}).values() if p
        }
        held_after = set(str(p) for p in fixed["bench"]) | {
            str(p) for p in (fixed.get("starters") or {}).values() if p
        }
        if held_before != held_after:
            raise SystemExit(
                f"{slug}: repair changes the roster: "
                f"lost {sorted(held_before - held_after)} "
                f"gained {sorted(held_after - held_before)}"
            )

        restored = [p for p in fixed["bench"] if p not in
                    {str(x) for x in (current.get("bench") or [])}]
        repaired.append({
            "team": slug,
            "duplicates_removed": [f"{s}:{p}" for s, p in dupes],
            "players_restored": restored,
            "bench_before": [str(p) for p in (current.get("bench") or [])],
            "bench_after": fixed["bench"],
        })
        if not args.dry_run:
            path.write_text(json.dumps(fixed, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")

    for r in repaired:
        print(f"{r['team']}:")
        print(f"    duplicates removed : {', '.join(r['duplicates_removed'])}")
        print(f"    players restored   : {', '.join(r['players_restored']) or '(none)'}")
        print(f"    bench {len(r['bench_before'])} -> {len(r['bench_after'])}")
    if not repaired:
        print("no corrupted rosters found")
    elif args.dry_run:
        print(f"\n(dry run: {len(repaired)} roster(s) would be rewritten)")
    else:
        print(f"\nrewrote {len(repaired)} roster(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""apply_trades.py — execute the week's accepted trade offers.

    python scripts/apply_trades.py --week 7
    python scripts/apply_trades.py --week 7 --dry-run

waivers.md §6: runs after the FAAB apply, which moves rosters first. Reads
``trade-screen.json`` and each target's ``decisions/<slug>.trade.json``,
applies every accepted offer on both rosters through
``lib.trades.apply_accepted`` and logs it to ``state/transactions.jsonl``.
When one team's accepted offers conflict, that team's GM chooses which to
honour in its own ``gm_turn.py`` turn (office.py's chooser). Counters are
recorded, never applied. ``--dry-run`` reports without writing and asks no GM.

The same step office.py's waivers stage runs in-process; this is its
command-line form, so the unattended routine can run it as one script.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.trades import apply_accepted  # noqa: E402
from office import _choose_between_conflicting_accepts  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply the week's accepted trades.")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would apply; write nothing, ask no GM")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    choose = None if args.dry_run else _choose_between_conflicting_accepts(
        root, args.season, args.week)
    results = apply_accepted(root, args.season, args.week,
                             dry_run=args.dry_run, choose=choose)
    if not results:
        print("no trade responses to apply")
        return 0
    for rec in results:
        if rec.get("applied"):
            print(f"applied {rec.get('from')} <-> {rec['target']}")
        else:
            print(f"{rec['target']}: {rec.get('reason', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

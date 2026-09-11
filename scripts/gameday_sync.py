#!/usr/bin/env python3
"""gameday_sync.py — pull live Sleeper stats for the current ops week.

Used by GitHub Actions and /refresh-board. Not the Commissioner 9am job.
Does not commit. Does not write Sleeper.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from lib.apply_gate import load_ops  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync live stats for the board.")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--season", default="2026")
    ap.add_argument("--week", type=int)
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    ops = load_ops(root)
    week = args.week or ops.get("week")
    season = args.season or ops.get("season") or "2026"
    if not week:
        print("no week in ops; pass --week", file=sys.stderr)
        return 1

    sync = root / "scripts" / "sync_sleeper.py"
    stats = subprocess.call([
        sys.executable, str(sync),
        "--stats", "--week", str(week), "--season", str(season),
    ])
    if stats != 0:
        return stats
    return subprocess.call([
        sys.executable, str(sync),
        "--schedule", "--week", str(week), "--season", str(season),
    ])


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""daily_ops.py — Commissioner's public slate check (scripts decide the day).

    python scripts/daily_ops.py
    python scripts/daily_ops.py --date 2026-09-13

Prints JSON: action, week, window, wake lists. No GM files.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.daily_ops import ops_for_root  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Today's DuPont Bowl op from the NFL slate")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--season", default="2026")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else date.today()
    call = ops_for_root(pathlib.Path(args.root), today=today, season=args.season)
    json.dump(call, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

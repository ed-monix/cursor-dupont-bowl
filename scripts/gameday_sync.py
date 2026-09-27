#!/usr/bin/env python3
"""gameday_sync.py — pull live Sleeper stats for the week being played.

Used by GitHub Actions and /refresh-board. Not the Commissioner 9am job.
Does not commit. Does not write Sleeper.

The week comes from the NFL schedule and today's date in US Eastern time, not
from state/ops/latest.json. latest.json was only ever written by the old Cursor
daily-ops path; once that stopped, it froze on week 2 and this job spent all of
week 3 re-syncing week 2 -- Thursday's ATL @ GB was never captured and the live
board went dark. The schedule knows which week a date belongs to; nothing has
to remember to tell it.

Eastern, not UTC, because the runner is UTC and the slate is not. Monday Night
Football kicks off at 00:15 UTC on *Tuesday*: a UTC date finds no games
"today", rolls forward to the next Thursday, and syncs next week in the middle
of the game this one is meant to be watching.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from lib.apply_gate import load_ops  # noqa: E402
from lib.daily_ops import week_for_date  # noqa: E402


def eastern_today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:  # no tz database: UTC is wrong for ~5h a night, not fatal
        return dt.datetime.now(dt.timezone.utc).date()


def live_week(root: pathlib.Path, today: Optional[dt.date] = None) -> Optional[int]:
    """The NFL week `today` belongs to, from the full season schedule."""
    try:
        data = json.loads((root / "state" / "nfl-schedule.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    games = data if isinstance(data, list) else (data or {}).get("games") or []
    return week_for_date(games, today or eastern_today())


def resolve_week(root: pathlib.Path, explicit: Optional[int] = None,
                 today: Optional[dt.date] = None) -> Optional[int]:
    """--week wins; then the schedule; then latest.json as a last resort."""
    if explicit:
        return explicit
    return live_week(root, today) or load_ops(root).get("week")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync live stats for the board.")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--season", default="2026")
    ap.add_argument("--week", type=int)
    ap.add_argument("--print-week", action="store_true",
                    help="print the week this would sync and exit (commit label)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    week = resolve_week(root, args.week)
    season = args.season or load_ops(root).get("season") or "2026"
    if args.print_week:
        print(week or "")
        return 0
    if not week:
        print("could not tell which week it is; pass --week", file=sys.stderr)
        return 1
    print(f"gameday_sync: week {week}")

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

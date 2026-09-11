#!/usr/bin/env python3
"""commish_gate.py — Commissioner is the only Bot that writes the league repo.

    python scripts/commish_gate.py daily --date 2026-09-13 --write
    python scripts/commish_gate.py ingest --week 1 --kind lineups-main \\
        --slug costanza --reply-file /tmp/costanza.json

GMs report JSON to the Commissioner. This script validates, then writes
state/ops/ and state/weeks/.../decisions/. Invalid replies stay out of git.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.commish_gate import ingest_reply  # noqa: E402
from lib.daily_ops import ops_for_root, write_ops  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def cmd_daily(root: pathlib.Path, day: str | None, season: str, write: bool) -> int:
    from datetime import date
    today = date.fromisoformat(day) if day else date.today()
    call = ops_for_root(root, today=today, season=season)
    if write:
        dest = write_ops(root, call)
        print(f"wrote {dest}", file=sys.stderr)
    json.dump(call, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_ingest(root: pathlib.Path, args) -> int:
    raw = pathlib.Path(args.reply_file).read_text(encoding="utf-8")
    record = ingest_reply(
        root,
        raw=raw,
        slug=args.slug,
        kind=args.kind,
        week=args.week,
        window=args.window,
        season=args.season,
        ops_day=args.date,
    )
    json.dump(record, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if record["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Commissioner git gate")
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_d = sub.add_parser("daily")
    p_d.add_argument("--date")
    p_d.add_argument("--season", default="2026")
    p_d.add_argument("--write", action="store_true")
    p_i = sub.add_parser("ingest")
    p_i.add_argument("--week", type=int, required=True)
    p_i.add_argument("--kind", required=True)
    p_i.add_argument("--slug", required=True)
    p_i.add_argument("--reply-file", required=True)
    p_i.add_argument("--window", choices=("early", "main"))
    p_i.add_argument("--season", default="2026")
    p_i.add_argument("--date", help="ops day YYYY-MM-DD")
    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.cmd == "daily":
        return cmd_daily(root, args.date, args.season, args.write)
    if args.cmd == "ingest":
        return cmd_ingest(root, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

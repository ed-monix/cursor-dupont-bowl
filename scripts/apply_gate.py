#!/usr/bin/env python3
"""apply_gate.py — Cloud Agent apply after the gate commits decisions/ to main.

    python scripts/apply_gate.py
    python scripts/apply_gate.py --dry-run

Reads state/ops/latest.json. Does not git commit. Does not write Sleeper.
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

from lib.apply_gate import (  # noqa: E402
    collect_waiver_claims,
    load_ops,
    standings_worst_to_best,
    week_dir,
)


def _load(path: pathlib.Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_waivers(root: pathlib.Path, season: str, week: int, dry_run: bool) -> int:
    wdir = week_dir(root, season, week)
    claims = collect_waiver_claims(wdir / "decisions")
    claims_path = wdir / "claims-from-gate.json"
    order_path = wdir / "faab-standings-order.json"
    standings = _load(root / "state" / "standings.json", {"teams": {}})
    _write(claims_path, claims)
    _write(order_path, standings_worst_to_best(standings))
    cmd = [
        sys.executable,
        str(root / "scripts" / "faab.py"),
        "--claims", str(claims_path),
        "--standings", str(order_path),
        "--players", str(root / "state" / "players.json"),
        "--rosters-dir", str(root / "teams"),
        "--roster-config", str(root / "config" / "roster.json"),
        "--report-out", str(wdir / "faab-report.json"),
        "--transactions", str(root / "state" / "transactions.jsonl"),
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(" ".join(cmd))
    return subprocess.call(cmd)


def apply_lineups(root: pathlib.Path, season: str, week: int,
                  window: str, dry_run: bool) -> int:
    cmd = [
        sys.executable,
        str(root / "scripts" / "lineups.py"),
        "--week", str(week),
        "--window", window,
        "--season", season,
        "--root", str(root),
        "--decisions-dir", str(week_dir(root, season, week) / "decisions"),
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(" ".join(cmd))
    return subprocess.call(cmd)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply gated decisions (no agents).")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--action", help="override ops action")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    ops = load_ops(root)
    action = args.action or ops.get("action") or "idle"
    week = int(ops.get("week") or 0)
    season = str(ops.get("season") or "2026")
    window = ops.get("window")
    print(json.dumps({"action": action, "week": week, "window": window}, sort_keys=True))

    if action in (None, "idle"):
        print("idle — nothing to apply")
        return 0
    if action == "recap":
        print("recap is /recap, not apply_gate")
        return 0
    if not week:
        print("ops has no week", file=sys.stderr)
        return 1
    if action == "waivers":
        return apply_waivers(root, season, week, args.dry_run)
    if action == "lineups-early":
        return apply_lineups(root, season, week, "early", args.dry_run)
    if action == "lineups-main":
        return apply_lineups(root, season, week, "main", args.dry_run)
    if action == "lineups":
        return apply_lineups(root, season, week, window or "main", args.dry_run)

    print(f"unknown action {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

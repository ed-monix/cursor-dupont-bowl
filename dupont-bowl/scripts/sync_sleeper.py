#!/usr/bin/env python3
"""sync_sleeper.py — pull league settings, players, projections, stats from Sleeper.

BUILD AGENT: finish per TASKS.md 1.1. --settings and --players below are a
working reference implementation and define the file contracts; add
--projections, --stats, --all, and the 24h .cache/ layer.

Usage:
  python scripts/sync_sleeper.py --league <id> --settings
  python scripts/sync_sleeper.py --players
"""
import argparse, json, pathlib, sys
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.sleeper.app/v1"
KEEP_POS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def sync_settings(league_id: str) -> None:
    lg = requests.get(f"{API}/league/{league_id}", timeout=30)
    lg.raise_for_status()
    data = lg.json()
    (ROOT / "config" / "scoring.json").write_text(
        json.dumps(data["scoring_settings"], indent=2))
    (ROOT / "config" / "roster.json").write_text(
        json.dumps({"roster_positions": data["roster_positions"],
                    "settings": data.get("settings", {})}, indent=2))
    print("wrote config/scoring.json, config/roster.json")


def sync_players() -> None:
    r = requests.get(f"{API}/players/nfl", timeout=120)  # ~5MB
    r.raise_for_status()
    trimmed = {}
    for pid, p in r.json().items():
        if p.get("position") in KEEP_POS and p.get("active"):
            trimmed[pid] = {
                "name": p.get("full_name") or f'{p.get("first_name","")} {p.get("last_name","")}'.strip(),
                "pos": p["position"],
                "team": p.get("team"),
                "status": p.get("status"),
                "injury": p.get("injury_status"),
            }
    out = ROOT / "state" / "players.json"
    out.write_text(json.dumps(trimmed, indent=1))
    print(f"wrote {out} ({len(trimmed)} players)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--settings", action="store_true")
    ap.add_argument("--players", action="store_true")
    # BUILD AGENT: --projections/--stats/--week/--all per TASKS.md 1.1
    a = ap.parse_args()
    if a.settings:
        if not a.league:
            sys.exit("--settings requires --league <reference_league_id>")
        sync_settings(a.league)
    if a.players:
        sync_players()
    if not (a.settings or a.players):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

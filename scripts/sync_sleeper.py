#!/usr/bin/env python3
"""sync_sleeper.py — pull league settings, players, projections, stats from Sleeper.

Usage:
  python scripts/sync_sleeper.py --league <id> --settings
  python scripts/sync_sleeper.py --players
  python scripts/sync_sleeper.py --projections --week <N> [--season <S>]
  python scripts/sync_sleeper.py --stats --week <N> [--season <S>]
  python scripts/sync_sleeper.py --all [--league <id>] [--week <N>] [--season <S>]
"""
import argparse, json, pathlib, sys, time
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.sleeper.app/v1"
KEEP_POS = {"QB", "RB", "WR", "TE", "K", "DEF"}
CACHE_DIR = ROOT / ".cache"
PLAYERS_CACHE_FILE = CACHE_DIR / "players_nfl.json"
CACHE_TTL = 86400  # 24 hours


def get_cache_dir() -> pathlib.Path:
    """Ensure .cache directory exists."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR


def is_cache_fresh(file_path: pathlib.Path) -> bool:
    """Check if cache file exists and is younger than TTL."""
    if not file_path.exists():
        return False
    age = time.time() - file_path.stat().st_mtime
    return age < CACHE_TTL


def get_nfl_state() -> dict:
    """Fetch current NFL season/week state."""
    r = requests.get(f"{API}/state/nfl", timeout=30)
    r.raise_for_status()
    return r.json()


def sync_settings(league_id: str) -> None:
    """Write config/scoring.json and config/roster.json from league."""
    lg = requests.get(f"{API}/league/{league_id}", timeout=30)
    lg.raise_for_status()
    data = lg.json()
    (ROOT / "config" / "scoring.json").write_text(
        json.dumps(data["scoring_settings"], indent=2))
    (ROOT / "config" / "roster.json").write_text(
        json.dumps({"roster_positions": data["roster_positions"],
                    "settings": data.get("settings", {})}, indent=2))
    print("wrote config/scoring.json, config/roster.json")


def sync_settings_standard() -> None:
    """Activate Sleeper-standard settings WITHOUT a reference league.

    Sleeper's API only exposes scoring per-league (there is no "defaults"
    endpoint), but config/scoring.default.json already encodes Sleeper's
    standard half-PPR scoring verbatim. This promotes that shipped default to
    the active config/scoring.json and writes the standard 12-team roster, so
    no reference league needs to be created for standard play.
    """
    default = json.loads((ROOT / "config" / "scoring.default.json").read_text())
    scoring = {k: v for k, v in default.items() if not k.startswith("_")}
    (ROOT / "config" / "scoring.json").write_text(json.dumps(scoring, indent=2))
    roster_positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF",
                        "BN", "BN", "BN", "BN", "BN", "BN", "IR"]
    (ROOT / "config" / "roster.json").write_text(json.dumps(
        {"roster_positions": roster_positions,
         "settings": {"num_teams": 12, "playoff_teams": 6,
                      "playoff_week_start": 15, "waiver_type": 2,
                      "waiver_budget": 100}}, indent=2))
    print("wrote config/scoring.json + config/roster.json (Sleeper standard; no reference league)")


def fetch_players_raw() -> dict:
    """Fetch raw players dump from Sleeper API (~5MB)."""
    r = requests.get(f"{API}/players/nfl", timeout=120)
    r.raise_for_status()
    return r.json()


def sync_players() -> None:
    """Write trimmed state/players.json with 24h caching of raw dump."""
    cache_file = get_cache_dir() / "players_nfl.json"

    # Load from cache if fresh
    if is_cache_fresh(cache_file):
        print(f"using cached players ({cache_file})")
        players_data = json.loads(cache_file.read_text())
    else:
        print("fetching players from API...")
        players_data = fetch_players_raw()
        cache_file.write_text(json.dumps(players_data))
        print(f"cached players to {cache_file}")

    # Trim to active skill positions + K + DEF
    trimmed = {}
    for pid, p in players_data.items():
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


def ensure_week_dir(season: str, week: int) -> pathlib.Path:
    """Create and return state/weeks/<season>-w<NN>/ directory."""
    week_dir = ROOT / "state" / "weeks" / f"{season}-w{week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    return week_dir


def sync_projections(season: str, week: int) -> None:
    """Fetch and write state/weeks/<season>-w<NN>/projections.json."""
    url = f"{API}/projections/nfl/regular/{season}/{week}"
    print(f"fetching projections from {url}...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    week_dir = ensure_week_dir(season, week)
    out = week_dir / "projections.json"
    out.write_text(json.dumps(data, indent=1))
    print(f"wrote {out} ({len(data)} rows)")


def sync_stats(season: str, week: int) -> None:
    """Fetch and write state/weeks/<season>-w<NN>/stats.json."""
    url = f"{API}/stats/nfl/regular/{season}/{week}"
    print(f"fetching stats from {url}...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    week_dir = ensure_week_dir(season, week)
    out = week_dir / "stats.json"
    out.write_text(json.dumps(data, indent=1))
    print(f"wrote {out} ({len(data)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync Sleeper data")
    ap.add_argument("--league", help="League ID for --settings")
    ap.add_argument("--settings", action="store_true", help="Activate scoring/roster settings: with --league, mirror that league; without, use Sleeper standard (no reference league needed)")
    ap.add_argument("--players", action="store_true", help="Sync player list (cached 24h)")
    ap.add_argument("--projections", action="store_true", help="Sync weekly projections")
    ap.add_argument("--stats", action="store_true", help="Sync weekly stats")
    ap.add_argument("--week", type=int, help="Week number for projections/stats")
    ap.add_argument("--season", help="Season (default: current from /state/nfl)")
    ap.add_argument("--all", action="store_true", help="Run settings (if league given), players, and current week projections+stats")

    a = ap.parse_args()

    if a.settings:
        if a.league:
            sync_settings(a.league)   # mirror a specific league's custom settings
        else:
            sync_settings_standard()  # standard half-PPR, no reference league needed

    if a.players:
        sync_players()

    if a.projections or a.stats:
        if not a.week:
            sys.exit("--projections and --stats require --week <N>")

        season = a.season
        if not season:
            state = get_nfl_state()
            season = state["season"]

        if a.projections:
            sync_projections(season, a.week)
        if a.stats:
            sync_stats(season, a.week)

    if a.all:
        if a.league:
            sync_settings(a.league)
        else:
            sync_settings_standard()
        sync_players()

        state = get_nfl_state()
        season = a.season or state["season"]
        week = a.week or state["week"]

        sync_projections(season, week)
        sync_stats(season, week)

    if not any([a.settings, a.players, a.projections, a.stats, a.all]):
        ap.print_help()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

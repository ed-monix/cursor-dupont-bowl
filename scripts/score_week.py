#!/usr/bin/env python3
"""Score all matchups for a given week and optionally update standings.

Pure logic functions are separated from I/O for testability:
- score_matchup(): compute winner and points for one matchup
- fold_week_into_standings(): update all team records from a week's matchups
- mark_week_official(): idempotent marking of week as finalized

CLI: score_week.py --week N [--season SEASON] [--final]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from lib.scoring import score_lineup


def score_matchup(
    home_team: str,
    away_team: str,
    home_roster: dict,
    away_roster: dict,
    stats: dict,
    scoring: dict,
) -> dict:
    """Score a single matchup and return the result.

    Returns {
        "home": home_team,
        "away": away_team,
        "home_score": float,
        "away_score": float,
        "home_lineup": {player_id: points, ...},
        "away_lineup": {player_id: points, ...},
        "winner": home_team | away_team | "tie"
    }
    """
    home_lineup = score_lineup(home_roster, stats, scoring)
    away_lineup = score_lineup(away_roster, stats, scoring)

    home_score = home_lineup.pop("total")
    away_score = away_lineup.pop("total")

    if home_score > away_score:
        winner = home_team
    elif away_score > home_score:
        winner = away_team
    else:
        winner = "tie"

    return {
        "home": home_team,
        "away": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "home_lineup": home_lineup,
        "away_lineup": away_lineup,
        "winner": winner,
    }


def fold_week_into_standings(
    standings: dict, matchups: list[dict], week: int
) -> dict:
    """Update standings from a list of scored matchups.

    For each matchup, updates the home and away teams' W/L/T record and PF/PA.
    Returns the updated standings dict. Assumes standings has a "teams" key
    mapping team_slug -> {wins, losses, ties, points_for, points_against}.

    Does not mutate input; returns new/updated dict.
    """
    if "teams" not in standings:
        standings = {"teams": {}}

    # Deep copy to avoid mutating input
    standings = json.loads(json.dumps(standings))

    for matchup in matchups:
        home = matchup["home"]
        away = matchup["away"]
        home_score = matchup["home_score"]
        away_score = matchup["away_score"]
        winner = matchup["winner"]

        # Ensure both teams exist in standings
        if home not in standings["teams"]:
            standings["teams"][home] = {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0.0,
                "points_against": 0.0,
            }
        if away not in standings["teams"]:
            standings["teams"][away] = {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0.0,
                "points_against": 0.0,
            }

        # Update records
        if winner == "tie":
            standings["teams"][home]["ties"] += 1
            standings["teams"][away]["ties"] += 1
        elif winner == home:
            standings["teams"][home]["wins"] += 1
            standings["teams"][away]["losses"] += 1
        else:  # winner == away
            standings["teams"][away]["wins"] += 1
            standings["teams"][home]["losses"] += 1

        # Update points for/against
        standings["teams"][home]["points_for"] += home_score
        standings["teams"][home]["points_against"] += away_score
        standings["teams"][away]["points_for"] += away_score
        standings["teams"][away]["points_against"] += home_score

    return standings


def mark_week_official(standings: dict, week: int, season: int) -> dict:
    """Mark a week as officially scored in standings, idempotently.

    Adds week to an "official_weeks" list if not already present. Idempotent:
    calling twice with the same week/season produces the same result as once.
    """
    if "official_weeks" not in standings:
        standings["official_weeks"] = []

    if week not in standings["official_weeks"]:
        standings["official_weeks"].append(week)
        standings["official_weeks"].sort()

    return standings


def fold_if_not_official(standings: dict, matchups: list[dict], week: int, season: int) -> dict:
    """Fold a week into standings only if not already official (idempotent guard).

    This is the pure-logic version of the main() guard: it folds the week
    only if week is not in official_weeks, then marks it official. Calling
    this twice with the same inputs produces the same result as calling once.

    Returns updated standings.
    """
    if "official_weeks" not in standings:
        standings["official_weeks"] = []

    if week not in standings["official_weeks"]:
        standings = fold_week_into_standings(standings, matchups, week)

    standings = mark_week_official(standings, week, season)
    return standings


def load_schedule(schedule_path: Path, week: int) -> list:
    """Load schedule.json and return matchups for the given week.

    Handles the schedule_gen.py shape:
    {"regular_season": {"1": [...], ..., "14": [...]},
     "playoffs": {"15": [...], "16": [...], "17": [...]}}

    For regular season weeks (1-14), returns matchups from regular_season.
    For playoff weeks (15-17), returns matchups from playoffs, filtering out
    any unresolved placeholders (e.g., "seed_3", "winner_15_1") that reference
    games not yet played. Returns only pairs where both entries are real team
    slugs with rosters.

    Also handles old flat shape (back-compat): {"weeks": {"1": [...], ...}}

    Raises FileNotFoundError if schedule not found; ValueError if week not
    found or has no resolvable matchups.
    """
    with open(schedule_path) as f:
        schedule = json.load(f)

    # Handle both old flat shape (for back-compat) and real schedule_gen shape
    if "regular_season" in schedule or "playoffs" in schedule:
        # Real schedule_gen shape
        if week <= 14:
            source = schedule.get("regular_season", {})
        else:
            source = schedule.get("playoffs", {})
    else:
        # Old flat shape (fallback, not canonical)
        source = schedule.get("weeks", schedule)

    week_key = str(week)
    if week_key not in source:
        raise ValueError(f"No matchups found for week {week}")

    matchups = source[week_key]

    # For playoffs, filter out unresolved placeholders (they'll be filled
    # after standings finalize, but during live scoring they can be skipped).
    if week >= 15:
        matchups = [
            pair
            for pair in matchups
            if not (pair[0].startswith("seed_") or pair[0].startswith("winner_"))
            and not (pair[1].startswith("seed_") or pair[1].startswith("winner_"))
        ]

    return matchups


def load_roster(team_path: Path, slug: str) -> dict:
    """Load teams/<slug>/roster.json."""
    roster_file = team_path / slug / "roster.json"
    if not roster_file.exists():
        raise FileNotFoundError(f"No roster found at {roster_file}")
    with open(roster_file) as f:
        return json.load(f)


def load_stats(weeks_path: Path, season: int, week: int) -> dict:
    """Load state/weeks/<season>-w<NN>/stats.json."""
    stats_file = weeks_path / f"{season}-w{week:02d}" / "stats.json"
    if not stats_file.exists():
        raise FileNotFoundError(f"No stats found at {stats_file}")
    with open(stats_file) as f:
        return json.load(f)


def load_scoring(config_path: Path) -> dict:
    """Load config/scoring.json; fall back to config/scoring.default.json."""
    scoring_file = config_path / "scoring.json"
    if not scoring_file.exists():
        scoring_file = config_path / "scoring.default.json"
    if not scoring_file.exists():
        raise FileNotFoundError("No scoring config found")
    with open(scoring_file) as f:
        raw = json.load(f)
    # Drop non-scoring keys (like "_comment")
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_standings(standings_path: Path) -> dict:
    """Load state/standings.json; return empty structure if not found."""
    if standings_path.exists():
        with open(standings_path) as f:
            return json.load(f)
    return {"season": None, "teams": {}}


def save_matchups(matchups_path: Path, matchups: list[dict], week: int, season: int):
    """Write state/weeks/<season>-w<NN>/matchups.json."""
    matchups_path.mkdir(parents=True, exist_ok=True)
    output = {"season": season, "week": week, "matchups": matchups}
    with open(matchups_path / "matchups.json", "w") as f:
        json.dump(output, f, indent=2)


def save_standings(standings_path: Path, standings: dict):
    """Write state/standings.json."""
    standings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(standings_path, "w") as f:
        json.dump(standings, f, indent=2)


def infer_season_and_week(schedule_path: Path, week: int) -> tuple[int, int]:
    """Infer season from schedule.json; default to current NFL season (2026)."""
    try:
        with open(schedule_path) as f:
            schedule = json.load(f)
    except FileNotFoundError:
        # No schedule yet; use default
        return (2026, week)

    season = schedule.get("season")
    if season is None:
        # Try to infer from week labels in the schedule
        season = 2026
    return (season, week)


def main():
    parser = argparse.ArgumentParser(
        description="Score all matchups for a week and optionally update standings."
    )
    parser.add_argument("--week", type=int, required=True, help="Week number (1-17)")
    parser.add_argument(
        "--season", type=int, default=None, help="Season (default: infer from schedule)"
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="Mark week official and update standings",
    )

    args = parser.parse_args()

    # Determine repo root (assume script is at scripts/score_week.py)
    repo_root = Path(__file__).resolve().parent.parent

    # Infer season if not provided
    if args.season is None:
        season, _ = infer_season_and_week(repo_root / "state" / "schedule.json", args.week)
    else:
        season = args.season

    week = args.week

    # Paths
    state_path = repo_root / "state"
    teams_path = repo_root / "teams"
    config_path = repo_root / "config"
    weeks_path = state_path / "weeks"
    schedule_path = state_path / "schedule.json"
    standings_path = state_path / "standings.json"

    try:
        # Load data
        matchups_list = load_schedule(schedule_path, week)
        scoring = load_scoring(config_path)
        stats = load_stats(weeks_path, season, week)

        # Score each matchup
        scored_matchups = []
        for home_team, away_team in matchups_list:
            home_roster = load_roster(teams_path, home_team)
            away_roster = load_roster(teams_path, away_team)

            matchup = score_matchup(
                home_team, away_team, home_roster, away_roster, stats, scoring
            )
            scored_matchups.append(matchup)

        # Write matchups
        save_matchups(weeks_path / f"{season}-w{week:02d}", scored_matchups, week, season)

        # Update standings if --final (idempotently via fold_if_not_official)
        if args.final:
            standings = load_standings(standings_path)
            if standings.get("season") is None:
                standings["season"] = season
            standings = fold_if_not_official(standings, scored_matchups, week, season)
            save_standings(standings_path, standings)

        print(f"Scored week {week} ({len(scored_matchups)} matchups)")
        if args.final:
            print(f"Updated standings and marked week {week} official")

    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

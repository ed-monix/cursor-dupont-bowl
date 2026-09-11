#!/usr/bin/env python3
"""dryrun.py -- deterministic fake-week harness (TASKS.md rework item 6).

Runs the full weekly pipeline -- FAAB, two lineup windows (early + main,
with a forced fallback on main), score_week, and live/final reconciliation
-- against committed fixtures under `tests/dryrun/` (a 4-team / 2-matchup
mini league). Every input is a committed file; there are no live GM
subagents and no network calls anywhere in this script. It exists to prove
the deterministic half of the pipeline (faab -> lineups windows ->
score_week -> reconcile) runs end-to-end and produces the exact expected
state (PLAN.md §4, TASKS.md "Definition of done").

This is thin orchestration over the existing libs (`scripts/faab.py`,
`scripts/free_agents.py`, `scripts/league_board.py`, `scripts/score_week.py`,
`scripts/lib/apply_lineups.py`, `scripts/lib/rosters.py`,
`scripts/lib/reconcile.py`, `scripts/lib/decisions.py`, `scripts/lib/packs.py`)
-- no scoring/validation/resolution logic is reimplemented here.

Steps, against `--root` (default `tests/dryrun`), week 1 of season 2026:

  1. Derive `state/free-agents.json` and `state/league-board.json` from the
     fixture rosters/players/projections (smoke check: both write cleanly).
  2. FAAB: resolve the canned waiver claims + standings, apply the winners
     via `lib.rosters.apply_transaction`, and write
     `state/transactions.jsonl` -- every emitted entry is validated against
     `docs/schemas/transaction-entry.json` via `lib.decisions`. Rebuild the
     league board after claims land.
  3. Lineups early: canned legal lineups; KC (Thursday) slots freeze.
     Packs are rebuilt as a smoke check (no GM files required).
  4. Lineups main: canned Sunday lineups. team-d's illegal double-start
     falls back (frozen Thursday slots held). team-a tries to move a
     frozen WR2; merge keeps the locked player (not a fallback).
  5. `score_week`: score week 1 as final, writing `matchups.json` and
     folding the results into `state/standings.json`.
  6. Reconcile the committed `live-scores.json` fixture against the final
     per-player scores just computed, and confirm the planted drift is
     exactly what's expected.

Mutates the fixture tree it's pointed at (rosters, transactions, standings,
etc.) -- this is a one-shot "run of the week" over `--root`, same as a real
`/waivers` + `/lineups early` + `/lineups main` + `/recap` run mutates the
real league root. Point it at a scratch copy (see `scripts/lib/test_dryrun.py`)
to run it repeatedly without touching the committed fixtures.

CLI:

    python scripts/dryrun.py [--root tests/dryrun]

Exits 0 and prints a pass summary on success; exits 1 (message on stderr)
on the first failed step or assertion.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import faab  # noqa: E402
import free_agents  # noqa: E402
import league_board  # noqa: E402
import score_week  # noqa: E402
from lib import decisions  # noqa: E402
from lib.apply_lineups import apply_lineup_window  # noqa: E402
from lib.rosters import save_roster  # noqa: E402
from lib.reconcile import reconcile  # noqa: E402
from lib import packs  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "tests" / "dryrun"

SEASON = 2026
WEEK = 1
WEEK_LABEL = f"{SEASON}-w{WEEK:02d}"

# The fixture is hand-worked (see tests/dryrun and the docstrings above) so
# the expected outcome of every step is known exactly -- these constants are
# what "produces the expected state" is checked against.
EXPECTED_WINNERS = {("team-a", "team-b"): "team-a", ("team-c", "team-d"): "team-c"}
EXPECTED_FALLBACK_TEAMS = {"team-d"}
EXPECTED_DRIFT_PLAYERS = {"wr-c1", "k-d"}
RECONCILE_THRESHOLD = 0.5


class DryRunFailure(RuntimeError):
    """Raised when a step's output doesn't match what the fixture demands."""


def _load_json(path: pathlib.Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def _load_rosters(teams_dir: pathlib.Path) -> dict:
    rosters = {}
    for roster_path in sorted(teams_dir.glob("*/roster.json")):
        slug = roster_path.parent.name
        if slug.startswith("_"):
            continue
        rosters[slug] = _load_json(roster_path)
    return rosters


# ---------------------------------------------------------------------------
# Step 1 -- free_agents + league_board (smoke: files written, no error)
# ---------------------------------------------------------------------------

def step_free_agents_and_board(root: pathlib.Path, players: dict, scoring: dict) -> dict:
    teams_dir = root / "teams"
    week_dir = root / "state" / "weeks" / WEEK_LABEL

    rosters = _load_rosters(teams_dir)
    projections = _load_json(week_dir / "projections.json")

    agents_pool = free_agents.derive_free_agents(players, rosters, projections, scoring)
    board = league_board.derive_league_board(rosters, players, projections, scoring)

    _write_json(root / "state" / "free-agents.json", agents_pool)
    _write_json(root / "state" / "league-board.json", board)

    if not agents_pool:
        raise DryRunFailure("free_agents: expected at least one free agent in the pool")
    if set(board) != set(rosters):
        raise DryRunFailure(
            f"league_board: expected teams {sorted(rosters)}, got {sorted(board)}"
        )

    return {"free_agents": agents_pool, "league_board": board}


# ---------------------------------------------------------------------------
# Step 2 -- FAAB: resolve canned claims, apply winners, validate the log
# ---------------------------------------------------------------------------

def step_faab(root: pathlib.Path, players: dict) -> dict:
    week_dir = root / "state" / "weeks" / WEEK_LABEL
    canned_dir = week_dir / "canned"
    teams_dir = root / "teams"

    claims_by_team = _load_json(canned_dir / "saturday-claims.json")
    standings_order = _load_json(canned_dir / "saturday-standings.json")
    rosters = _load_rosters(teams_dir)

    report = faab.resolve_faab(claims_by_team, standings_order, rosters, players)
    updated_rosters, entries = faab.apply_won_claims(report, rosters, players)

    schema = decisions.load_schema("transaction-entry")
    for entry in entries:
        errors = decisions.validate(entry, schema)
        if errors:
            raise DryRunFailure(
                f"faab: transaction entry failed docs/schemas/transaction-entry.json: "
                f"{errors} -- entry: {entry}"
            )

    faab.write_results(updated_rosters, entries, teams_dir, root / "state" / "transactions.jsonl")
    _write_json(week_dir / "faab-report.json", report)

    won = [c for c in report["claims"] if c["status"] == "won"]
    lost = [c for c in report["claims"] if c["status"] == "lost"]
    if not won:
        raise DryRunFailure("faab: expected at least one won claim (collision resolution unproven)")
    if not lost:
        raise DryRunFailure("faab: expected at least one lost claim (collision fixture didn't collide)")
    if len(entries) != len(won):
        raise DryRunFailure(
            f"faab: expected one transaction entry per won claim ({len(won)}), got {len(entries)}"
        )

    return {"report": report, "entries": entries, "won": won, "lost": lost}


def _rebuild_board(root: pathlib.Path, players: dict, scoring: dict) -> dict:
    week_dir = root / "state" / "weeks" / WEEK_LABEL
    rosters = _load_rosters(root / "teams")
    projections = _load_json(week_dir / "projections.json")
    board = league_board.derive_league_board(rosters, players, projections, scoring)
    _write_json(root / "state" / "league-board.json", board)
    return board


def _write_rosters(teams_dir: pathlib.Path, rosters: dict) -> None:
    for slug, roster in rosters.items():
        save_roster(roster, teams_dir / slug / "roster.json")


# ---------------------------------------------------------------------------
# Step 3 -- lineup windows (early then main) + pack smoke
# ---------------------------------------------------------------------------

def step_lineups(root: pathlib.Path, players: dict) -> dict:
    teams_dir = root / "teams"
    week_dir = root / "state" / "weeks" / WEEK_LABEL
    projections = _load_json(week_dir / "projections.json")
    scoring = score_week.load_scoring(root / "config")
    games = _load_json(week_dir / "nfl-games.json")
    board = _rebuild_board(root, players, scoring)

    buzz_dir = root / "state" / "news" / "buzz"
    buzz_dir.mkdir(parents=True, exist_ok=True)
    (buzz_dir / f"{WEEK_LABEL}.md").write_text("SECRET_BUZZ_MUST_NOT_REACH_GMS\n")
    public = packs.build_public_pack(root, WEEK, str(SEASON))
    if not public.get("nfl_games"):
        raise DryRunFailure("packs: expected nfl_games on the public pack")
    private = packs.build_private_pack(
        root, "team-a", WEEK, str(SEASON), public=public, run="lineups", window="early",
    )
    blob = json.dumps(private) + packs.render_gm_prompt(private)
    if "SECRET_BUZZ_MUST_NOT_REACH_GMS" in blob:
        raise DryRunFailure("packs: GMs must never see state/news/buzz/")

    early = apply_lineup_window(
        _load_rosters(teams_dir), players, projections, scoring,
        _load_json(week_dir / "canned" / "lineups-early.json"),
        "early", games, existing_lineups={}, board=board,
    )
    _write_json(week_dir / "lineups.json", early["lineups"])
    _write_rosters(teams_dir, early["rosters"])

    team_a_locked = set((early["lineups"]["team-a"].get("locked_slots") or {}))
    if "WR2" not in team_a_locked:
        raise DryRunFailure("lineups-early: expected team-a WR2 (KC / Thursday) to freeze")
    if "WR2" in (early["lineups"]["team-d"].get("locked_slots") or {}):
        raise DryRunFailure("lineups-early: team-d is Sunday-only and must stay unlocked")

    # TNF is now in progress; main window still cannot move those slots.
    for game in games:
        if game.get("home") == "KC" or game.get("away") == "KC":
            game["status"] = "complete"
    _write_json(week_dir / "nfl-games.json", games)
    board = _rebuild_board(root, players, scoring)

    main = apply_lineup_window(
        _load_rosters(teams_dir), players, projections, scoring,
        _load_json(week_dir / "canned" / "sunday-lineups.json"),
        "main", games, existing_lineups=early["lineups"], board=board,
    )
    _write_json(week_dir / "lineups.json", main["lineups"])
    _write_rosters(teams_dir, main["rosters"])

    fallback_teams = [
        slug for slug, entry in main["lineups"].items() if entry.get("fallback")
    ]
    if set(fallback_teams) != EXPECTED_FALLBACK_TEAMS:
        raise DryRunFailure(
            f"lineups-main: expected fallback for {sorted(EXPECTED_FALLBACK_TEAMS)}, "
            f"got {sorted(fallback_teams)}"
        )
    if main["lineups"]["team-a"]["starters"]["WR2"] != "wr-a2":
        raise DryRunFailure("lineups-main: frozen team-a WR2 must stay wr-a2")
    a_report = next(t for t in main["report"]["teams"] if t["team"] == "team-a")
    if not a_report["freeze_violations"]:
        raise DryRunFailure("lineups-main: expected freeze_violations on team-a's WR2 swap")
    if a_report["fallback"]:
        raise DryRunFailure("lineups-main: moving a frozen slot is not a fallback")

    return {
        "lineups": main["lineups"],
        "fallback_teams": fallback_teams,
        "early": early,
        "main": main,
        "pack_prompt_bytes": packs.pack_sizes(public, private)["prompt_bytes"],
    }


# ---------------------------------------------------------------------------
# Step 4 -- score_week --final: matchups.json + standings.json
# ---------------------------------------------------------------------------

def step_score_week(root: pathlib.Path) -> dict:
    state_dir = root / "state"
    teams_dir = root / "teams"
    config_dir = root / "config"
    weeks_dir = state_dir / "weeks"
    schedule_path = state_dir / "schedule.json"
    standings_path = state_dir / "standings.json"

    matchups_list = score_week.load_schedule(schedule_path, WEEK)
    scoring = score_week.load_scoring(config_dir)
    stats = score_week.load_stats(weeks_dir, SEASON, WEEK)

    scored = []
    for home, away in matchups_list:
        home_roster = score_week.load_roster(teams_dir, home)
        away_roster = score_week.load_roster(teams_dir, away)
        scored.append(
            score_week.score_matchup(home, away, home_roster, away_roster, stats, scoring)
        )

    week_dir = weeks_dir / WEEK_LABEL
    score_week.save_matchups(week_dir, scored, WEEK, SEASON)

    standings = score_week.load_standings(standings_path)
    if standings.get("season") is None:
        standings["season"] = SEASON
    standings = score_week.fold_if_not_official(standings, scored, WEEK, SEASON)
    score_week.save_standings(standings_path, standings)

    if len(scored) != len(EXPECTED_WINNERS):
        raise DryRunFailure(
            f"score_week: expected {len(EXPECTED_WINNERS)} matchups, got {len(scored)}"
        )
    for matchup in scored:
        key = (matchup["home"], matchup["away"])
        expected = EXPECTED_WINNERS.get(key)
        if expected is None:
            raise DryRunFailure(f"score_week: unexpected matchup {key}")
        if matchup["winner"] != expected:
            raise DryRunFailure(
                f"score_week: {key} expected winner {expected!r}, got {matchup['winner']!r}"
            )

    teams_in_standings = standings.get("teams", {})
    for slug in EXPECTED_FALLBACK_TEAMS | {t for pair in EXPECTED_WINNERS for t in pair}:
        if slug not in teams_in_standings:
            raise DryRunFailure(f"score_week: standings missing team {slug!r}")
        record = teams_in_standings[slug]
        if record["wins"] + record["losses"] + record["ties"] != 1:
            raise DryRunFailure(f"score_week: {slug} should have exactly 1 game recorded")
    if WEEK not in standings.get("official_weeks", []):
        raise DryRunFailure(f"score_week: week {WEEK} not marked official in standings")

    return {"matchups": scored, "standings": standings}


# ---------------------------------------------------------------------------
# Step 5 -- reconcile the committed live-scores.json fixture against finals
# ---------------------------------------------------------------------------

def step_reconcile(root: pathlib.Path) -> dict:
    week_dir = root / "state" / "weeks" / WEEK_LABEL

    matchups = _load_json(week_dir / "matchups.json")["matchups"]
    final_scores: dict = {}
    for matchup in matchups:
        final_scores.update(matchup["home_lineup"])
        final_scores.update(matchup["away_lineup"])

    live_scores = _load_json(week_dir / "live-scores.json")

    drift = reconcile(live_scores, final_scores, threshold=RECONCILE_THRESHOLD)
    drifted_ids = {record["player_id"] for record in drift}

    if drifted_ids != EXPECTED_DRIFT_PLAYERS:
        raise DryRunFailure(
            f"reconcile: expected drift on {sorted(EXPECTED_DRIFT_PLAYERS)}, "
            f"got {sorted(drifted_ids)}"
        )
    for record in drift:
        if abs(record["delta"]) <= RECONCILE_THRESHOLD:
            raise DryRunFailure(
                f"reconcile: {record['player_id']} delta {record['delta']} does not "
                f"exceed the {RECONCILE_THRESHOLD} threshold"
            )

    return {"drift": drift, "final_scores": final_scores, "live_scores": live_scores}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(root: pathlib.Path) -> dict:
    """Run every step in order against `root`. Returns a dict of per-step
    results (see each step_* function). Raises DryRunFailure (or lets a
    lower-level ValueError/FileNotFoundError propagate) on the first
    failure -- nothing after that step runs."""
    root = pathlib.Path(root)
    players = _load_json(root / "state" / "players.json")
    scoring = score_week.load_scoring(root / "config")

    results = {}
    results["free_agents_and_board"] = step_free_agents_and_board(root, players, scoring)
    results["faab"] = step_faab(root, players)
    results["lineups"] = step_lineups(root, players)
    results["score_week"] = step_score_week(root)
    results["reconcile"] = step_reconcile(root)
    return results


def _print_summary(results: dict) -> None:
    fa = results["free_agents_and_board"]
    faab_r = results["faab"]
    lineups = results["lineups"]
    sw = results["score_week"]
    rec = results["reconcile"]

    print("PASS -- dry run week", WEEK, f"({SEASON})")
    print(
        f"  [1] free agents: {len(fa['free_agents'])} available; "
        f"league board: {len(fa['league_board'])} teams"
    )
    print(
        f"  [2] faab: {len(faab_r['won'])} won / {len(faab_r['lost'])} lost claim(s); "
        f"{len(faab_r['entries'])} transaction(s) logged, all schema-valid"
    )
    print(
        f"  [3] lineups: fallback triggered for {sorted(lineups['fallback_teams'])}; "
        f"early pack prompt {lineups['pack_prompt_bytes']} bytes"
    )
    for matchup in sw["matchups"]:
        print(
            f"  [4] {matchup['home']} {matchup['home_score']:.1f} - "
            f"{matchup['away_score']:.1f} {matchup['away']} "
            f"(winner: {matchup['winner']})"
        )
    print(
        f"  [5] reconcile: {len(rec['drift'])} player(s) drifted beyond "
        f"{RECONCILE_THRESHOLD} pts: {[r['player_id'] for r in rec['drift']]}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic fake-week harness: committed fixtures only, no network/agents."
    )
    ap.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="league root to run against (default: tests/dryrun)",
    )
    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)

    print(f"dryrun: root={root} season={SEASON} week={WEEK}")
    try:
        results = run(root)
    except DryRunFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    _print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())

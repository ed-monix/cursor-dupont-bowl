#!/usr/bin/env python3
"""dryrun.py -- deterministic fake-week harness (TASKS.md rework item 6).

Runs the full weekly pipeline -- FAAB, Sunday lineups (with a forced
fallback), score_week, and live/final reconciliation -- against committed
fixtures under `tests/dryrun/` (a 4-team / 2-matchup mini league). Every
input is a committed file; there are no live GM subagents and no network
calls anywhere in this script. It exists to prove the deterministic half of
the pipeline (faab -> apply -> score_week -> reconcile) runs end-to-end and
produces the exact expected state (PLAN.md §4, TASKS.md "Definition of
done").

This is thin orchestration over the existing libs (`scripts/faab.py`,
`scripts/free_agents.py`, `scripts/league_board.py`, `scripts/score_week.py`,
`scripts/lib/rosters.py`, `scripts/lib/reconcile.py`,
`scripts/lib/decisions.py`) -- no scoring/validation/resolution logic is
reimplemented here.

Steps, against `--root` (default `tests/dryrun`), week 1 of season 2026:

  1. Derive `state/free-agents.json` and `state/league-board.json` from the
     fixture rosters/players/projections (smoke check: both write cleanly).
  2. FAAB: resolve the canned Saturday claims + standings, apply the winners
     via `lib.rosters.apply_transaction`, and write
     `state/transactions.jsonl` -- every emitted entry is validated against
     `docs/schemas/transaction-entry.json` via `lib.decisions`.
  3. Sunday: apply each team's canned lineup; any lineup that fails
     `lib.rosters.validate_lineup` (this fixture deliberately breaks one:
     team-d starts the same player in two slots) falls back to
     `lib.rosters.best_legal_lineup` and is flagged `fallback: true` in the
     written `state/weeks/<...>/lineups.json`.
  4. `score_week`: score week 1 as final, writing `matchups.json` and
     folding the results into `state/standings.json`.
  5. Reconcile the committed `live-scores.json` fixture against the final
     per-player scores just computed, and confirm the planted drift is
     exactly what's expected.

Mutates the fixture tree it's pointed at (rosters, transactions, standings,
etc.) -- this is a one-shot "run of the week" over `--root`, same as a real
`/saturday` + `/sunday` + `/recap` run mutates the real league root. Point
it at a scratch copy (see `scripts/lib/test_dryrun.py`) to run it repeatedly
without touching the committed fixtures.

CLI:

    python scripts/dryrun.py [--root tests/dryrun]

Exits 0 and prints a pass summary on success; exits 1 (message on stderr)
on the first failed step or assertion.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import faab  # noqa: E402
import free_agents  # noqa: E402
import league_board  # noqa: E402
import score_week  # noqa: E402
from lib import decisions  # noqa: E402
from lib.rosters import (  # noqa: E402
    best_legal_lineup,
    save_roster,
    validate_lineup,
)
from lib.reconcile import reconcile  # noqa: E402

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


# ---------------------------------------------------------------------------
# Step 3 -- Sunday lineups, forcing + flagging the fallback path
# ---------------------------------------------------------------------------

def step_sunday(root: pathlib.Path, players: dict) -> dict:
    teams_dir = root / "teams"
    week_dir = root / "state" / "weeks" / WEEK_LABEL
    canned_lineups = _load_json(week_dir / "canned" / "sunday-lineups.json")
    projections = _load_json(week_dir / "projections.json")
    scoring = score_week.load_scoring(root / "config")

    rosters = _load_rosters(teams_dir)

    lineups_out = {}
    fallback_teams = []

    for slug, roster in sorted(rosters.items()):
        canned = canned_lineups.get(slug)
        if canned is None:
            ok, errors = False, ["no canned lineup submitted for this team"]
            candidate = roster
        else:
            candidate = copy.deepcopy(roster)
            candidate["starters"] = dict(canned["starters"])
            ok, errors = validate_lineup(candidate, players)

        used_fallback = False
        if ok:
            justification = canned.get("justification", "")
        else:
            used_fallback = True
            candidate = best_legal_lineup(roster, players, projections, scoring)
            ok2, errors2 = validate_lineup(candidate, players)
            if not ok2:
                raise DryRunFailure(
                    f"sunday: {slug} fallback lineup is still illegal: {errors2}"
                )
            justification = (
                "FALLBACK (highest-projected legal lineup): submitted lineup was "
                "illegal -- " + "; ".join(errors)
            )

        save_roster(candidate, teams_dir / slug / "roster.json")
        lineups_out[slug] = {
            "starters": candidate["starters"],
            "justification": justification,
            "fallback": used_fallback,
        }
        if used_fallback:
            fallback_teams.append(slug)

    _write_json(week_dir / "lineups.json", lineups_out)

    if not fallback_teams:
        raise DryRunFailure(
            "sunday: expected the fallback path to be exercised for at least one team"
        )
    if set(fallback_teams) != EXPECTED_FALLBACK_TEAMS:
        raise DryRunFailure(
            f"sunday: expected fallback for {sorted(EXPECTED_FALLBACK_TEAMS)}, "
            f"got {sorted(fallback_teams)}"
        )

    return {"lineups": lineups_out, "fallback_teams": fallback_teams}


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
    results["sunday"] = step_sunday(root, players)
    results["score_week"] = step_score_week(root)
    results["reconcile"] = step_reconcile(root)
    return results


def _print_summary(results: dict) -> None:
    fa = results["free_agents_and_board"]
    faab_r = results["faab"]
    sunday = results["sunday"]
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
    print(f"  [3] sunday: fallback triggered for {sorted(sunday['fallback_teams'])}")
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

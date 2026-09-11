"""Tests for scripts/dryrun.py (TASKS.md rework item 6 -- the deterministic
dry-run harness).

Runs the full dryrun end-to-end against a **copy** of the committed
`tests/dryrun/` fixtures in `tmp_path`, so the committed fixture tree is
never dirtied by running the suite (dryrun.py mutates the root it's pointed
at -- rosters, transactions.jsonl, standings.json, etc. -- exactly like a
real weekly run would). Hermetic: no network, no live agents, no writes
outside `tmp_path`.

Import note: this file lives under scripts/lib/ (repo convention: pytest
adds scripts/ to sys.path because scripts/lib/__init__.py exists, so lib.*
imports work; dryrun.py lives directly under scripts/, one level up from
scripts/lib/, so `import dryrun` also just works from here, same as
`import faab` does in test_faab.py).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import dryrun

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "dryrun"


@pytest.fixture
def dryrun_root(tmp_path) -> Path:
    """A throwaway copy of tests/dryrun under tmp_path."""
    dest = tmp_path / "dryrun"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


def _read(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Fixture sanity: the committed tree itself must never be touched by the
# suite -- run once at the top so any leak is caught before it can mask
# other test failures via ordering.
# ---------------------------------------------------------------------------

def test_committed_fixtures_are_untouched_by_a_run(dryrun_root):
    before = _read(FIXTURE_ROOT / "state" / "standings.json")
    rc = dryrun.main(["--root", str(dryrun_root)])
    assert rc == 0
    after = _read(FIXTURE_ROOT / "state" / "standings.json")
    assert before == after == {"season": 2026, "official_weeks": [], "teams": {}}


# ---------------------------------------------------------------------------
# End-to-end: one run, all the assertions the task calls for.
# ---------------------------------------------------------------------------

def test_dryrun_end_to_end(dryrun_root):
    rc = dryrun.main(["--root", str(dryrun_root)])
    assert rc == 0

    week_dir = dryrun_root / "state" / "weeks" / "2026-w01"

    # --- step 1: derived files exist and are non-trivial -------------------
    free_agents = _read(dryrun_root / "state" / "free-agents.json")
    league_board = _read(dryrun_root / "state" / "league-board.json")
    assert free_agents  # at least one free agent in the pool
    assert set(league_board) == {"team-a", "team-b", "team-c", "team-d"}

    # --- step 2: transactions validate against the schema ------------------
    from lib import decisions

    schema = decisions.load_schema("transaction-entry")
    transactions = _read_jsonl(dryrun_root / "state" / "transactions.jsonl")
    assert len(transactions) == 2  # team-b wins fa-1, team-c wins fa-2 (hand-worked)
    for entry in transactions:
        assert decisions.validate(entry, schema) == []
    by_team = {t["team"]: t for t in transactions}
    assert by_team["team-b"]["action"] == "waiver_claim"
    assert by_team["team-b"]["players"] == ["fa-1", "bn-b2"]
    assert by_team["team-b"]["bid"] == 20
    assert by_team["team-b"]["status"] == "applied"
    assert by_team["team-c"]["players"] == ["fa-2", "bn-c1"]
    assert by_team["team-c"]["bid"] == 15

    # the tied bidder (team-a, lost the tiebreak to worse-standing team-b)
    # and the outbid team (team-d) spent nothing and rostered nothing new.
    team_a_roster = _read(dryrun_root / "teams" / "team-a" / "roster.json")
    team_d_roster = _read(dryrun_root / "teams" / "team-d" / "roster.json")
    assert team_a_roster["faab_remaining"] == 100
    assert "fa-1" not in team_a_roster["bench"]
    assert team_d_roster["faab_remaining"] == 100
    assert "fa-2" not in team_d_roster["bench"]

    # winners paid their bid and rostered the add.
    team_b_roster = _read(dryrun_root / "teams" / "team-b" / "roster.json")
    team_c_roster = _read(dryrun_root / "teams" / "team-c" / "roster.json")
    assert team_b_roster["faab_remaining"] == 80
    assert "fa-1" in team_b_roster["bench"]
    assert team_c_roster["faab_remaining"] == 85
    assert "fa-2" in team_c_roster["bench"]

    # --- step 3: two lineup windows; forced fallback + freeze hold ---------
    lineups = _read(week_dir / "lineups.json")
    assert lineups["team-d"]["fallback"] is True
    assert "FALLBACK" in lineups["team-d"]["justification"]
    for slug in ("team-a", "team-b", "team-c"):
        assert lineups[slug]["fallback"] is False
    assert "early" in lineups["team-a"]["windows_run"]
    assert "main" in lineups["team-a"]["windows_run"]
    assert "WR2" in lineups["team-a"]["locked_slots"]
    assert lineups["team-a"]["starters"]["WR2"] == "wr-a2"
    # team-d is Sunday-only: unlocked after early, locked after main
    assert "WR2" in lineups["team-d"]["locked_slots"]

    from lib.rosters import validate_lineup

    players = _read(dryrun_root / "state" / "players.json")
    for slug in ("team-a", "team-b", "team-c", "team-d"):
        roster = _read(dryrun_root / "teams" / slug / "roster.json")
        ok, errors = validate_lineup(roster, players)
        assert ok, f"{slug}: {errors}"

    # team-d's canned lineup illegally double-started wr-d1 (WR1 + FLEX);
    # the fallback lineup must not repeat that mistake.
    team_d_starters = lineups["team-d"]["starters"]
    assert len(set(team_d_starters.values())) == len(team_d_starters)

    # --- step 4: standings reflect the two results --------------------------
    matchups = _read(week_dir / "matchups.json")["matchups"]
    assert {(m["home"], m["away"]): m["winner"] for m in matchups} == {
        ("team-a", "team-b"): "team-a",
        ("team-c", "team-d"): "team-c",
    }
    home_away_scores = {(m["home"], m["away"]): (m["home_score"], m["away_score"]) for m in matchups}
    assert home_away_scores[("team-a", "team-b")] == pytest.approx((88.0, 53.8))
    assert home_away_scores[("team-c", "team-d")] == pytest.approx((103.8, 68.1))

    standings = _read(dryrun_root / "state" / "standings.json")
    assert standings["official_weeks"] == [1]
    assert standings["teams"]["team-a"] == {
        "wins": 1, "losses": 0, "ties": 0,
        "points_for": pytest.approx(88.0), "points_against": pytest.approx(53.8),
    }
    assert standings["teams"]["team-b"] == {
        "wins": 0, "losses": 1, "ties": 0,
        "points_for": pytest.approx(53.8), "points_against": pytest.approx(88.0),
    }
    assert standings["teams"]["team-c"] == {
        "wins": 1, "losses": 0, "ties": 0,
        "points_for": pytest.approx(103.8), "points_against": pytest.approx(68.1),
    }
    assert standings["teams"]["team-d"] == {
        "wins": 0, "losses": 1, "ties": 0,
        "points_for": pytest.approx(68.1), "points_against": pytest.approx(103.8),
    }

    # --- step 5: reconcile finds exactly the planted drift -------------------
    live_scores = _read(week_dir / "live-scores.json")
    final_scores = {}
    for m in matchups:
        final_scores.update(m["home_lineup"])
        final_scores.update(m["away_lineup"])

    from lib.reconcile import reconcile

    records = reconcile(live_scores, final_scores, threshold=0.5)
    assert {r["player_id"] for r in records} == {"wr-c1", "k-d"}
    by_player = {r["player_id"]: r for r in records}
    assert by_player["wr-c1"]["delta"] == pytest.approx(3.5)
    assert by_player["wr-c1"]["live"] == pytest.approx(15.0)
    assert by_player["wr-c1"]["final"] == pytest.approx(18.5)
    assert by_player["k-d"]["delta"] == pytest.approx(1.5)


def test_dryrun_cli_help():
    """python scripts/dryrun.py --help works (repo convention: every script
    is runnable as `python scripts/<name>.py --help`, TASKS.md header)."""
    with pytest.raises(SystemExit) as exc_info:
        dryrun.main(["--help"])
    assert exc_info.value.code == 0


def test_dryrun_fails_loudly_on_a_broken_root(tmp_path):
    """An empty/missing root is a FileNotFoundError-shaped failure, not a
    silent no-op -- confirms main() turns that into a clean nonzero exit."""
    rc = dryrun.main(["--root", str(tmp_path / "does-not-exist")])
    assert rc == 1

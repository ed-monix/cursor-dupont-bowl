"""Tests for scripts/faab.py. Pure, no network, no external files (the
write_results test uses pytest's tmp_path, still no real repo files touched).

Import note: this file lives under scripts/lib/ (repo convention: pytest adds
scripts/ to sys.path because scripts/lib/__init__.py exists, so lib.* imports
work). faab.py itself lives directly under scripts/, one level up from
scripts/lib/ -- but that same sys.path entry (scripts/) makes it a plain
top-level import too, so `import faab` works from here without any path
hacking.
"""

import json

import pytest

import faab
from lib.rosters import validate_roster


# ---------------------------------------------------------------------------
# Fixtures shared across tests
# ---------------------------------------------------------------------------

def make_players(**overrides):
    base = {
        "p1": {"name": "Player One", "pos": "WR", "team": "AAA", "status": "Active", "injury": None},
        "p2": {"name": "Player Two", "pos": "RB", "team": "AAA", "status": "Active", "injury": None},
        "p3": {"name": "Player Three", "pos": "WR", "team": "AAA", "status": "Active", "injury": None},
        "p4": {"name": "Player Four", "pos": "TE", "team": "AAA", "status": "Active", "injury": None},
        "p5": {"name": "Player Five", "pos": "RB", "team": "AAA", "status": "Active", "injury": None},
    }
    base.update(overrides)
    return base


def make_roster(team, faab, bench=()):
    """Minimal roster shape sufficient for resolve_faab (which only reads
    faab_remaining and scans starters/bench/ir for drop-presence -- it does
    not require a fully slot-legal roster; that's apply_transaction's job,
    exercised separately below with full rosters)."""
    return {"team": team, "faab_remaining": faab, "starters": {}, "bench": list(bench), "ir": []}


# ---------------------------------------------------------------------------
# AC: 4-team collision scenario, hand-worked and asserted exactly.
# ---------------------------------------------------------------------------
#
# Standings (worst -> best): team-d, team-b, team-a, team-c
#   ranks: team-d=0 (worst), team-b=1, team-a=2, team-c=3 (best)
#
# Claims:
#   team-a: 1) add p1 drop dA1 bid 25    2) add p2 drop dA2 bid 10
#   team-b: 1) add p1 drop dB1 bid 25
#   team-c: 1) add p4 drop dC1 bid 40    2) add p5 drop dC1 bid 5
#   team-d: 1) add p2 drop dD1 bid 10
#
# Hand-worked resolution:
#
# p1 is bid on by team-a (25) and team-b (25) -- an exact tie. Worse
# standing wins: team-b (rank 1) is worse than team-a (rank 2), so team-b
# wins p1. team-a's claim #1 LOSES (tied, lost tiebreak).
#
# p2 is bid on by team-a (10) and team-d (10) -- also an exact tie. team-d
# (rank 0) is worse than team-a (rank 2), so team-d wins p2. team-a's claim
# #2 LOSES (tied, lost tiebreak). team-a therefore loses both its claims,
# spends nothing, keeps its full budget.
#
# p4 is uncontested (only team-c bid): team-c WINS at 40, drop dC1 consumed.
# p5 is uncontested (only team-c bid) but its drop (dC1) was already
# consumed by team-c's own prior winning claim this run -> SKIPPED.
#
# team-b WINS p1 at 25 (dropping dB1, which is on its roster) -> budget
# 60 - 25 = 35.
# team-c WINS p4 at 40 (dropping dC1) -> budget 100 - 40 = 60; claim #2
# skipped, no further deduction.
# team-d WINS p2 at 10 (dropping dD1, which is on its roster) -> budget
# 40 - 10 = 30.
#
# Final remaining_budget: team-a=50 (untouched), team-b=35, team-c=60,
# team-d=30.

def test_four_team_collision_hand_worked():
    players = make_players()
    standings = ["team-d", "team-b", "team-a", "team-c"]
    rosters = {
        "team-a": make_roster("team-a", faab=50, bench=["dA1", "dA2"]),
        "team-b": make_roster("team-b", faab=60, bench=["dB1"]),
        "team-c": make_roster("team-c", faab=100, bench=["dC1"]),
        "team-d": make_roster("team-d", faab=40, bench=["dD1"]),
    }
    claims_by_team = {
        "team-a": [
            {"add": "p1", "drop": "dA1", "bid": 25, "reasoning": "swing for p1"},
            {"add": "p2", "drop": "dA2", "bid": 10, "reasoning": "backup plan"},
        ],
        "team-b": [
            {"add": "p1", "drop": "dB1", "bid": 25, "reasoning": "also wants p1"},
        ],
        "team-c": [
            {"add": "p4", "drop": "dC1", "bid": 40, "reasoning": "big swing"},
            {"add": "p5", "drop": "dC1", "bid": 5, "reasoning": "same cut, different target"},
        ],
        "team-d": [
            {"add": "p2", "drop": "dD1", "bid": 10, "reasoning": "sneaky tie"},
        ],
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)

    def find(team, add_id):
        for c in report["claims"]:
            if c["team"] == team and c["add"] == add_id:
                return c
        raise AssertionError(f"no claim found for {team}/{add_id}")

    a1 = find("team-a", "p1")
    assert a1["status"] == "lost"
    assert a1["reason"] == "tied bid $25 for p1; lost tiebreak to team-b (worse standing wins)"

    a2 = find("team-a", "p2")
    assert a2["status"] == "lost"
    assert a2["reason"] == "tied bid $10 for p2; lost tiebreak to team-d (worse standing wins)"

    b1 = find("team-b", "p1")
    assert b1["status"] == "won"
    assert b1["reason"] == "highest bid $25 (next best $25)"

    c1 = find("team-c", "p4")
    assert c1["status"] == "won"
    assert c1["reason"] == "uncontested claim, bid $40"

    c2 = find("team-c", "p5")
    assert c2["status"] == "skipped"
    assert c2["reason"] == "drop player dC1 already used by an earlier claim this run"

    d1 = find("team-d", "p2")
    assert d1["status"] == "won"
    assert d1["reason"] == "highest bid $10 (next best $10)"

    assert report["remaining_budget"] == {
        "team-a": 50,
        "team-b": 35,
        "team-c": 60,
        "team-d": 30,
    }

    # Claim order within each team is preserved (priority order intact).
    team_a_claims = [c for c in report["claims"] if c["team"] == "team-a"]
    assert [c["add"] for c in team_a_claims] == ["p1", "p2"]
    team_c_claims = [c for c in report["claims"] if c["team"] == "team-c"]
    assert [c["add"] for c in team_c_claims] == ["p4", "p5"]


# ---------------------------------------------------------------------------
# Budget deduction correctness + a bid exceeding remaining budget skipped.
# ---------------------------------------------------------------------------

def test_budget_deducted_on_win_and_overspend_skipped():
    players = make_players()
    standings = ["team-a"]
    rosters = {"team-a": make_roster("team-a", faab=20, bench=["b1", "b2"])}
    claims_by_team = {
        "team-a": [
            {"add": "p1", "drop": "b1", "bid": 15, "reasoning": "first"},
            {"add": "p2", "drop": "b2", "bid": 10, "reasoning": "second, over budget"},
        ]
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)

    first, second = report["claims"]
    assert first["status"] == "won"
    assert second["status"] == "skipped"
    assert second["reason"] == "insufficient FAAB: bid $10 exceeds remaining $5"
    # Only the winning claim's bid was deducted (15), not the rejected one.
    assert report["remaining_budget"]["team-a"] == 5


def test_bid_of_zero_can_win_uncontested():
    players = make_players()
    standings = ["team-a"]
    rosters = {"team-a": make_roster("team-a", faab=100)}
    claims_by_team = {"team-a": [{"add": "p1", "drop": None, "bid": 0, "reasoning": "free"}]}

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    assert report["claims"][0]["status"] == "won"
    assert report["remaining_budget"]["team-a"] == 100


# ---------------------------------------------------------------------------
# A claim whose drop player is already gone -> skipped.
# ---------------------------------------------------------------------------

def test_drop_player_already_gone_is_skipped():
    players = make_players()
    standings = ["team-a"]
    # "ghost" is not anywhere on team-a's roster -- already gone.
    rosters = {"team-a": make_roster("team-a", faab=100, bench=["real_player"])}
    claims_by_team = {
        "team-a": [{"add": "p1", "drop": "ghost", "bid": 10, "reasoning": "oops"}]
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    claim = report["claims"][0]
    assert claim["status"] == "skipped"
    assert claim["reason"] == "drop player ghost not on roster (already gone)"
    # No budget deducted for a skipped claim.
    assert report["remaining_budget"]["team-a"] == 100


# ---------------------------------------------------------------------------
# Extra coverage: unknown add player, no-drop add, single-team no contest.
# ---------------------------------------------------------------------------

def test_unknown_add_player_is_skipped():
    players = make_players()
    standings = ["team-a"]
    rosters = {"team-a": make_roster("team-a", faab=100)}
    claims_by_team = {
        "team-a": [{"add": "not_a_real_player", "drop": None, "bid": 10, "reasoning": "typo"}]
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    claim = report["claims"][0]
    assert claim["status"] == "skipped"
    assert claim["reason"] == "unknown player id: not_a_real_player"
    assert report["remaining_budget"]["team-a"] == 100


def test_add_with_no_drop_needs_no_roster_check():
    players = make_players()
    standings = ["team-a"]
    rosters = {"team-a": make_roster("team-a", faab=100)}
    claims_by_team = {"team-a": [{"add": "p1", "drop": None, "bid": 5, "reasoning": "bench stash"}]}

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    assert report["claims"][0]["status"] == "won"
    assert report["remaining_budget"]["team-a"] == 95


# ---------------------------------------------------------------------------
# Apply step: separate from resolution, testable without disk.
# ---------------------------------------------------------------------------

def _full_players():
    """Players covering a full standard roster (see lib/rosters.py) plus
    two free agents to add."""
    pos_map = {
        "qb1": "QB", "rb1": "RB", "rb2": "RB", "rb3": "RB",
        "wr1": "WR", "wr2": "WR", "wr3": "WR",
        "te1": "TE", "k1": "K", "def1": "DEF",
        "fa_rb": "RB", "fa_wr": "WR",
    }
    return {
        pid: {"name": pid, "pos": pos, "team": "AAA", "status": "Active", "injury": None}
        for pid, pos in pos_map.items()
    }


def _full_roster(team, faab, bench):
    return {
        "team": team,
        "faab_remaining": faab,
        "starters": {
            "QB": "qb1", "RB1": "rb1", "RB2": "rb2", "WR1": "wr1", "WR2": "wr2",
            "TE": "te1", "FLEX": "rb3", "K": "k1", "DEF": "def1",
        },
        "bench": list(bench),
        "ir": [],
    }


def test_apply_won_claims_updates_roster_and_logs_transaction():
    players = _full_players()
    rosters = {
        "team-a": _full_roster("team-a", faab=50, bench=["wr3"]),
    }
    report = {
        "claims": [
            {"team": "team-a", "add": "fa_rb", "drop": "wr3", "bid": 12,
             "reasoning": "upgrade bench", "status": "won", "reason": "uncontested claim, bid $12"},
            {"team": "team-a", "add": "fa_wr", "drop": None, "bid": 3,
             "reasoning": "lost this one", "status": "lost", "reason": "outbid"},
        ]
    }

    updated, entries = faab.apply_won_claims(report, rosters, players, timestamp="2026-09-06T12:00:00+00:00")

    # Only the won claim was applied.
    assert "fa_rb" in updated["team-a"]["bench"]
    assert "wr3" not in updated["team-a"]["bench"]
    assert "fa_wr" not in updated["team-a"]["bench"]  # the lost claim never touches the roster

    # The winning bid was deducted from the roster's faab_remaining (the
    # lost claim's bid was not).
    assert updated["team-a"]["faab_remaining"] == 38

    # Resulting roster is still legal.
    ok, errors = validate_roster(updated["team-a"], players)
    assert ok, errors

    # Original roster dict passed in is untouched.
    assert rosters["team-a"]["bench"] == ["wr3"]

    assert entries == [{
        "timestamp": "2026-09-06T12:00:00+00:00",
        "team": "team-a",
        "action": "faab_add",
        "players": {"add": "fa_rb", "drop": "wr3"},
        "bid": 12,
        "reasoning": "upgrade bench",
        "status": "applied",
    }]


def test_apply_won_claims_no_won_claims_is_a_no_op():
    players = _full_players()
    rosters = {"team-a": _full_roster("team-a", faab=50, bench=["wr3"])}
    report = {"claims": [
        {"team": "team-a", "add": "fa_rb", "drop": "wr3", "bid": 12,
         "reasoning": None, "status": "skipped", "reason": "insufficient FAAB"},
    ]}

    updated, entries = faab.apply_won_claims(report, rosters, players)
    assert entries == []
    assert updated["team-a"] == rosters["team-a"]


# ---------------------------------------------------------------------------
# write_results: thin disk-writing wrapper (uses tmp_path, no repo files).
# ---------------------------------------------------------------------------

def test_write_results_saves_rosters_and_appends_transactions(tmp_path):
    rosters_dir = tmp_path / "teams"
    (rosters_dir / "team-a").mkdir(parents=True)
    transactions_path = tmp_path / "state" / "transactions.jsonl"
    # Pre-existing line to prove we append, not overwrite.
    transactions_path.parent.mkdir(parents=True)
    transactions_path.write_text('{"pre": "existing"}\n')

    updated_rosters = {"team-a": {"team": "team-a", "faab_remaining": 38,
                                   "starters": {}, "bench": ["fa_rb"], "ir": []}}
    entries = [{"timestamp": "2026-09-06T12:00:00+00:00", "team": "team-a",
                "action": "faab_add", "players": {"add": "fa_rb", "drop": "wr3"},
                "bid": 12, "reasoning": "upgrade bench", "status": "applied"}]

    faab.write_results(updated_rosters, entries, rosters_dir, transactions_path)

    saved = json.loads((rosters_dir / "team-a" / "roster.json").read_text())
    assert saved["bench"] == ["fa_rb"]
    assert saved["faab_remaining"] == 38

    lines = transactions_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"pre": "existing"}
    assert json.loads(lines[1])["team"] == "team-a"
    assert json.loads(lines[1])["action"] == "faab_add"


# ---------------------------------------------------------------------------
# Tiebreak sanity check in isolation (not just inside the 4-team scenario).
# ---------------------------------------------------------------------------

def test_worse_standing_wins_exact_tie():
    players = make_players()
    standings = ["worst-team", "mid-team", "best-team"]
    rosters = {
        "worst-team": make_roster("worst-team", faab=100),
        "best-team": make_roster("best-team", faab=100),
    }
    claims_by_team = {
        "worst-team": [{"add": "p1", "drop": None, "bid": 50, "reasoning": ""}],
        "best-team": [{"add": "p1", "drop": None, "bid": 50, "reasoning": ""}],
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    by_team = {c["team"]: c for c in report["claims"]}
    assert by_team["worst-team"]["status"] == "won"
    assert by_team["best-team"]["status"] == "lost"


def test_higher_bid_wins_over_worse_standing():
    """Standing only breaks exact ties; a strictly higher bid always wins
    regardless of standing."""
    players = make_players()
    standings = ["worst-team", "best-team"]
    rosters = {
        "worst-team": make_roster("worst-team", faab=100),
        "best-team": make_roster("best-team", faab=100),
    }
    claims_by_team = {
        "worst-team": [{"add": "p1", "drop": None, "bid": 5, "reasoning": ""}],
        "best-team": [{"add": "p1", "drop": None, "bid": 6, "reasoning": ""}],
    }

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    by_team = {c["team"]: c for c in report["claims"]}
    assert by_team["best-team"]["status"] == "won"
    assert by_team["worst-team"]["status"] == "lost"

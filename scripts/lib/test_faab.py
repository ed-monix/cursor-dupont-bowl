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
    """Minimal roster shape sufficient for resolve_faab.

    resolve_faab does check that a winning claim leaves a legal roster, but it
    only blames a claim for illegality the claim itself causes: a roster that is
    already invalid going in (like this one, which has no starters) is not the
    claim's fault, so the gate does not fire. Full-roster behaviour is exercised
    below with _full_roster."""
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

def test_claim_on_player_rostered_by_another_team_is_skipped():
    """Week 7 waivers: 11435 was on dumbledore, 96 on harry-caray.

    faab marked both claims won and apply would have put each player on a
    second roster. They are skipped, with the owner named, and nothing is
    charged. A legal claim in the same run still resolves.
    """
    players = _full_players()
    players["11435"] = {
        "name": "Rico Dowdle", "pos": "RB", "team": "CAR",
        "status": "Active", "injury": None,
    }
    players["96"] = {
        "name": "Aaron Rodgers", "pos": "QB", "team": "PIT",
        "status": "Active", "injury": None,
    }

    dumbledore = _full_roster("dumbledore", faab=22, bench=["wr3"])
    dumbledore["starters"]["RB2"] = "11435"
    harry = _full_roster("harry-caray", faab=40, bench=["wr3"])
    harry["starters"]["QB"] = "96"
    meyer = _full_roster("meyer-walsh", faab=14, bench=["wr3"])
    rinna = _full_roster("rinna", faab=55, bench=["wr3"])
    rosters = {
        "meyer-walsh": meyer,
        "rinna": rinna,
        "dumbledore": dumbledore,
        "harry-caray": harry,
    }
    claims_by_team = {
        "meyer-walsh": [{
            "add": "11435", "drop": "wr3", "bid": 13,
            "reasoning": "already on dumbledore",
        }],
        "rinna": [
            {"add": "96", "drop": "wr3", "bid": 10, "reasoning": "already on harry"},
            {"add": "fa_wr", "drop": None, "bid": 1, "reasoning": "actual free agent"},
        ],
    }
    standings = ["meyer-walsh", "rinna", "dumbledore", "harry-caray"]

    report = faab.resolve_faab(claims_by_team, standings, rosters, players)
    by_key = {(c["team"], c["add"]): c for c in report["claims"]}

    owned_rb = by_key[("meyer-walsh", "11435")]
    assert owned_rb["status"] == "skipped"
    assert owned_rb["reason"] == "player 11435 already rostered by dumbledore"

    owned_qb = by_key[("rinna", "96")]
    assert owned_qb["status"] == "skipped"
    assert owned_qb["reason"] == "player 96 already rostered by harry-caray"

    assert by_key[("rinna", "fa_wr")]["status"] == "won"
    assert report["remaining_budget"]["meyer-walsh"] == 14
    assert report["remaining_budget"]["rinna"] == 54

    updated, entries = faab.apply_won_claims(
        report, rosters, players, timestamp="2026-10-21T12:00:00+00:00",
    )
    assert [e["players"][0] for e in entries] == ["fa_wr"]
    assert "11435" not in updated["meyer-walsh"]["bench"]
    assert "11435" not in (updated["meyer-walsh"]["starters"] or {}).values()
    assert "96" not in updated["rinna"]["bench"]
    assert "96" not in (updated["rinna"]["starters"] or {}).values()
    assert updated["dumbledore"]["starters"]["RB2"] == "11435"
    assert updated["harry-caray"]["starters"]["QB"] == "96"
    assert "fa_wr" in updated["rinna"]["bench"]


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
        "action": "waiver_claim",
        "players": ["fa_rb", "wr3"],
        "bid": 12,
        "reasoning": "upgrade bench",
        "status": "applied",
    }]


def test_applied_entries_conform_to_transaction_schema():
    """Cross-check: every transaction entry faab.py emits validates against
    docs/schemas/transaction-entry.json (the league's declared log contract)."""
    from lib.decisions import load_schema, validate

    schema = load_schema("transaction-entry")
    players = _full_players()
    rosters = {"team-a": _full_roster("team-a", faab=50, bench=["wr3"])}
    report = {"claims": [
        {"team": "team-a", "add": "fa_rb", "drop": "wr3", "bid": 12,
         "reasoning": "upgrade bench", "status": "won", "reason": "uncontested"},
        {"team": "team-a", "add": "fa_wr", "drop": None, "bid": 0,
         "reasoning": None, "status": "won", "reason": "free stash"},  # None reasoning
    ]}

    _, entries = faab.apply_won_claims(report, rosters, players, timestamp="2026-09-06T12:00:00+00:00")

    assert len(entries) == 2
    for e in entries:
        assert validate(e, schema) == [], (e, validate(e, schema))
    # add-first ordering; drop appended only when present.
    assert entries[0]["action"] == "waiver_claim"
    assert entries[0]["players"] == ["fa_rb", "wr3"]
    assert entries[1]["players"] == ["fa_wr"]
    # A null reasoning is coerced to the empty string (schema requires a string).
    assert entries[1]["reasoning"] == ""


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


# ---------------------------------------------------------------------------
# A won claim that would leave an illegal roster is voided, not raised.
#
# This is what took down the first automated week-2 run: a GM claimed a DEF
# while dropping its STARTING DEF with a full bench. resolve_faab marked it
# "won", apply_won_claims raised out of the run, and nothing committed. Its own
# docstring says resolve_faab's checks should prevent that — this is the check
# that was missing.
# ---------------------------------------------------------------------------

def _bench_full(team, faab):
    """A legal roster whose bench is at the six-player limit."""
    r = _full_roster(team, faab, bench=["wr3", "b2", "b3", "b4", "b5", "b6"])
    return r


def _players_with_full_bench():
    players = _full_players()
    for pid in ("b2", "b3", "b4", "b5", "b6"):
        players[pid] = {"name": pid, "pos": "WR", "team": "AAA",
                        "status": "Active", "injury": None}
    return players


def test_claim_that_would_overflow_the_bench_is_voided_not_raised():
    players = _players_with_full_bench()
    rosters = {"team-a": _bench_full("team-a", faab=50)}
    # Dropping a STARTER empties a slot but frees no bench space, so the add
    # has nowhere to land.
    claims = {"team-a": [{"add": "fa_wr", "drop": "def1", "bid": 9,
                          "reasoning": "clear the decks"}]}

    report = faab.resolve_faab(claims, ["team-a"], rosters, players)
    claim = report["claims"][0]
    assert claim["status"] == "skipped"
    assert "illegal roster" in claim["reason"]

    # Voided, not charged — Ruling 2026-05 refunded a voided bid and the
    # commissioner's memos say "no FAAB is charged" for a struck claim.
    assert report["remaining_budget"]["team-a"] == 50

    # And the run survives: apply_won_claims has nothing illegal to choke on.
    updated, entries = faab.apply_won_claims(report, rosters, players)
    assert entries == []
    ok, errors = validate_roster(updated["team-a"], players)
    assert ok, errors


def test_a_legal_claim_on_the_same_roster_still_wins():
    """The gate must not become a blanket refusal."""
    players = _players_with_full_bench()
    rosters = {"team-a": _bench_full("team-a", faab=50)}
    claims = {"team-a": [{"add": "fa_wr", "drop": "b2", "bid": 9,
                          "reasoning": "bench for bench"}]}

    report = faab.resolve_faab(claims, ["team-a"], rosters, players)
    assert report["claims"][0]["status"] == "won"
    assert report["remaining_budget"]["team-a"] == 41
    updated, entries = faab.apply_won_claims(report, rosters, players)
    assert len(entries) == 1
    ok, errors = validate_roster(updated["team-a"], players)
    assert ok, errors


def test_one_voided_claim_does_not_sink_the_others():
    """The whole point: one GM's illegal claim must not stall the week."""
    players = _players_with_full_bench()
    rosters = {
        "team-a": _bench_full("team-a", faab=50),
        "team-b": _full_roster("team-b", faab=50, bench=["b2"]),
    }
    claims = {
        "team-a": [{"add": "fa_wr", "drop": "def1", "bid": 9, "reasoning": "illegal"}],
        "team-b": [{"add": "fa_rb", "drop": "b2", "bid": 4, "reasoning": "legal"}],
    }

    report = faab.resolve_faab(claims, ["team-a", "team-b"], rosters, players)
    by_team = {c["team"]: c for c in report["claims"]}
    assert by_team["team-a"]["status"] == "skipped"
    assert by_team["team-b"]["status"] == "won"

    updated, entries = faab.apply_won_claims(report, rosters, players)
    assert [e["team"] for e in entries] == ["team-b"]
    assert "fa_rb" in updated["team-b"]["bench"]


# ---------------------------------------------------------------------------
# Ruling 2026-10 (2026-10-22): a won claim fills an empty starting slot for
# its position before the bench. harry-caray's week 7 kicker claim crashed the
# apply because the K slot was empty and the bench was already over its limit.
# ---------------------------------------------------------------------------

def test_claim_fills_an_empty_position_slot_before_the_bench():
    players = _players_with_full_bench()
    players["fa_k"] = {"name": "fa_k", "pos": "K", "team": "AAA", "status": "Active", "injury": None}
    roster = _bench_full("team-a", faab=50)
    roster["starters"]["K"] = None
    assert faab.claim_target(roster, "fa_k", players) == "K"
    assert faab.claim_target(roster, "b2", players) == "bench"   # a WR: WR slots are full, FLEX is never auto-filled
    report = {"claims": [{"team": "team-a", "add": "fa_k", "drop": None, "bid": 1,
                          "reasoning": "need a kicker", "status": "won", "reason": "uncontested claim, bid $1"}]}
    updated, entries = faab.apply_won_claims(report, {"team-a": roster}, players,
                                             timestamp="2026-10-22T12:00:00+00:00")
    assert updated["team-a"]["starters"]["K"] == "fa_k"
    assert "fa_k" not in updated["team-a"]["bench"]
    assert len(updated["team-a"]["bench"]) == 6
    assert entries[0]["status"] == "applied"


def test_a_slot_freed_by_the_claims_own_drop_counts_as_empty():
    players = _players_with_full_bench()
    players["fa_k"] = {"name": "fa_k", "pos": "K", "team": "AAA", "status": "Active", "injury": None}
    roster = _bench_full("team-a", faab=50)
    old_k = roster["starters"]["K"]
    assert faab.claim_target(roster, "fa_k", players, drop_id=old_k) == "K"


# ---------------------------------------------------------------------------
# Ruling 2026-11 (2026-10-27): standalone drops land before that team's
# claims are checked for roster room.
#
# Week 8: costanza bid $9 on Jordan Mason with no drop on the claim, and
# listed two bench players as standalone drops. The bench was full (six).
# The engine checked the claim first, saw seven on the bench, and skipped
# it. your-team's $3 bid on the same player was outbid either way.
# ---------------------------------------------------------------------------

def _claims_for(report, team):
    return [c for c in report["claims"] if c["team"] == team]


def test_standalone_drops_free_a_full_bench_before_the_claim():
    """Full bench, claim with no drop, two standalone drops, top bid wins.

    The resulting bench is five: six, minus the two drops, plus the add.
    The lower bid stays lost and is not handed the player.
    """
    players = _players_with_full_bench()
    rosters = {
        "costanza": _bench_full("costanza", faab=67),
        "your-team": _full_roster("your-team", faab=3, bench=["wr3"]),
    }
    claims = {
        "costanza": [
            {"add": "fa_rb", "drop": None, "bid": 9, "reasoning": "nine bucks, not a penny more"},
        ],
        "your-team": [
            {"add": "fa_rb", "drop": "wr3", "bid": 3, "reasoning": "last three dollars"},
        ],
    }
    drops = {"costanza": ["b5", "b6"]}
    standings = ["costanza", "your-team"]

    report = faab.resolve_faab(
        claims, standings, rosters, players, drops_by_team=drops)

    costanza = _claims_for(report, "costanza")[0]
    assert costanza["status"] == "won"
    assert costanza["reason"] == "highest bid $9 (next best $3)"
    assert report["remaining_budget"]["costanza"] == 58

    your = _claims_for(report, "your-team")[0]
    assert your["status"] == "lost"
    assert your["reason"] == "outbid on fa_rb: costanza bid $9 (your bid $3)"
    assert report["remaining_budget"]["your-team"] == 3

    applied = [d for d in report["drops"] if d["status"] == "applied"]
    assert [(d["team"], d["player"]) for d in applied] == [
        ("costanza", "b5"), ("costanza", "b6"),
    ]

    updated, entries = faab.apply_won_claims(
        report, rosters, players, timestamp="2026-10-27T12:00:00+00:00")
    bench = updated["costanza"]["bench"]
    assert "b5" not in bench and "b6" not in bench
    assert "fa_rb" in bench
    assert len(bench) == 5
    assert updated["costanza"]["faab_remaining"] == 58
    assert "fa_rb" not in updated["your-team"]["bench"]
    assert updated["your-team"]["faab_remaining"] == 3
    ok, errors = validate_roster(updated["costanza"], players)
    assert ok, errors
    ok, errors = validate_roster(updated["your-team"], players)
    assert ok, errors

    from lib.decisions import load_schema, validate
    schema = load_schema("transaction-entry")
    assert [e["action"] for e in entries] == ["drop", "drop", "waiver_claim"]
    assert entries[0]["players"] == ["b5"]
    assert entries[1]["players"] == ["b6"]
    assert entries[2]["players"] == ["fa_rb"]
    assert entries[2]["bid"] == 9
    for entry in entries:
        assert validate(entry, schema) == [], (entry, validate(entry, schema))
    # The rosters handed in are not mutated.
    assert rosters["costanza"]["bench"] == ["wr3", "b2", "b3", "b4", "b5", "b6"]


def test_standalone_drops_do_not_change_other_teams_resolution():
    """One team's drops do not move another team's wins, losses, or budget.

    costanza is the top bid and, with the drops, can execute. Without them
    the claim is skipped. your-team is outbid either way and is not handed
    the player. wifes-team's claim on a different player is identical in
    both runs.
    """
    players = _players_with_full_bench()
    rosters = {
        "costanza": _bench_full("costanza", faab=67),
        "your-team": _full_roster("your-team", faab=3, bench=["wr3"]),
        "wifes-team": _full_roster("wifes-team", faab=36, bench=["b2"]),
    }
    claims = {
        "costanza": [
            {"add": "fa_rb", "drop": None, "bid": 9, "reasoning": "mason"},
        ],
        "your-team": [
            {"add": "fa_rb", "drop": "wr3", "bid": 3, "reasoning": "low"},
        ],
        "wifes-team": [
            {"add": "fa_wr", "drop": "b2", "bid": 10, "reasoning": "other player"},
        ],
    }
    standings = ["costanza", "your-team", "wifes-team"]

    with_drops = faab.resolve_faab(
        claims, standings, rosters, players,
        drops_by_team={"costanza": ["b5", "b6"]})
    without = faab.resolve_faab(claims, standings, rosters, players)

    assert _claims_for(with_drops, "costanza")[0]["status"] == "won"
    assert _claims_for(without, "costanza")[0]["status"] == "skipped"
    assert "illegal roster" in _claims_for(without, "costanza")[0]["reason"]

    assert _claims_for(with_drops, "your-team") == _claims_for(without, "your-team")
    assert _claims_for(with_drops, "your-team")[0]["status"] == "lost"
    assert _claims_for(with_drops, "wifes-team") == _claims_for(without, "wifes-team")
    assert _claims_for(with_drops, "wifes-team")[0]["status"] == "won"
    assert with_drops["remaining_budget"]["your-team"] == without["remaining_budget"]["your-team"] == 3
    assert with_drops["remaining_budget"]["wifes-team"] == without["remaining_budget"]["wifes-team"] == 26

    updated_with, _ = faab.apply_won_claims(with_drops, rosters, players)
    updated_without, _ = faab.apply_won_claims(without, rosters, players)
    assert updated_with["your-team"] == updated_without["your-team"]
    assert updated_with["wifes-team"] == updated_without["wifes-team"]
    assert "fa_rb" in updated_with["costanza"]["bench"]
    assert "fa_rb" not in updated_without["costanza"]["bench"]
    assert "fa_rb" not in updated_with["your-team"]["bench"]
    assert "fa_wr" in updated_with["wifes-team"]["bench"]


def test_standalone_drop_not_on_roster_is_skipped_and_frees_no_room():
    """A standalone drop of a player the team does not hold uses the same
    skip a claim drop of an absent player already uses, and does not open
    a bench spot."""
    players = _players_with_full_bench()
    rosters = {"costanza": _bench_full("costanza", faab=67)}
    claims = {"costanza": [
        {"add": "fa_rb", "drop": None, "bid": 9, "reasoning": "no room"},
    ]}

    report = faab.resolve_faab(
        claims, ["costanza"], rosters, players,
        drops_by_team={"costanza": ["ghost"]})

    assert report["drops"] == [{
        "team": "costanza",
        "player": "ghost",
        "status": "skipped",
        "reason": "drop player ghost not on roster (already gone)",
    }]
    claim = report["claims"][0]
    assert claim["status"] == "skipped"
    assert "bench has 7 players, limit is 6" in claim["reason"]
    assert report["remaining_budget"]["costanza"] == 67

    updated, entries = faab.apply_won_claims(report, rosters, players)
    assert entries == []
    assert updated["costanza"]["bench"] == rosters["costanza"]["bench"]

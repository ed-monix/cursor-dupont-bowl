"""free_agency.py: who is offered, and what a GM may not do with the window.

The cached free-agents.json is built before FAAB applies, so on week 5 it still
listed Aaron Rodgers after harry-caray won him. Candidates must come from the
rosters. The GM turn is mocked; these pin the script's side of the contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import free_agency  # noqa: E402
from lib import claude_turn  # noqa: E402

SLOTS = {"QB": "qb1", "RB1": "rb1", "RB2": "rb2", "WR1": "wr1", "WR2": "wr2",
         "TE": "te1", "FLEX": "rb3", "K": "k1", "DEF": "d1"}
POS = {"qb1": "QB", "qb2": "QB", "rb1": "RB", "rb2": "RB", "rb3": "RB",
       "wr1": "WR", "wr2": "WR", "te1": "TE", "k1": "K", "d1": "DEF",
       "b1": "WR", "b2": "WR", "b3": "WR", "b4": "WR", "b5": "WR",
       "fa_qb": "QB", "fa_hurt": "QB", "fa_early": "QB", "taken_qb": "QB"}
TEAM = {"fa_early": "LON"}


def _league(tmp_path, gm_reply, verdict="approve"):
    root = tmp_path
    w = root / "state" / "weeks" / "2026-w05"
    w.mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "roster.json").write_text(json.dumps({"roster_positions":
        ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 6 + ["IR"]}))
    (root / "config" / "scoring.json").write_text(json.dumps({}))
    players = {pid: {"name": pid, "pos": pos, "team": TEAM.get(pid, "AAA"),
                     "status": "Active", "injury": "Out" if pid == "fa_hurt" else None}
               for pid, pos in POS.items()}
    (root / "state" / "players.json").write_text(json.dumps(players))
    (w / "projections.json").write_text("{}")
    (w / "nfl-games.json").write_text(json.dumps([
        {"game_id": "g1", "home": "AAA", "away": "BBB", "date": "2026-10-11", "status": "pre_game"},
        {"game_id": "g2", "home": "LON", "away": "CCC", "date": "2026-10-11", "status": "in_game"},
    ]))
    for slug, starters, bench in (("me", SLOTS, ["qb2", "b1", "b2", "b3", "b4", "b5"]),
                                  ("them", {"QB": "taken_qb"}, [])):
        d = root / "teams" / slug
        d.mkdir(parents=True)
        (d / "roster.json").write_text(json.dumps(
            {"team": slug, "faab_remaining": 50, "starters": starters, "bench": bench, "ir": []}))
        (d / "general-manager.md").write_text("# GM\n")
    (root / "agents").mkdir()
    (root / "agents" / "commissioner.md").write_text("# Commissioner\n")
    seen = {}

    def fake_turn(**kw):
        if kw["label"].endswith("-fa-review"):
            seen["review_pack"] = json.loads(kw["user_text"])
            if verdict == "error":
                raise claude_turn.TurnError("review down")
            return claude_turn.TurnResult(text=json.dumps(
                {"verdict": verdict, "rule": None if verdict == "approve" else "x",
                 "signoff": "Fine."}), usage={})
        seen["pack"] = json.loads(kw["user_text"])
        return claude_turn.TurnResult(text=json.dumps(gm_reply), usage={})
    return root, seen, fake_turn


def _run(root, monkeypatch, fake_turn):
    monkeypatch.setattr(free_agency.claude_turn, "run_turn", fake_turn)
    return free_agency.main(["--team", "me", "--week", "5", "--pos", "QB",
                             "--root", str(root)])


def test_only_true_free_agents_whose_games_have_not_kicked_are_offered(tmp_path, monkeypatch):
    root, seen, fake = _league(tmp_path, {"add": None, "drop": None,
                                          "start_slot": None, "reasoning": "pat"})
    assert _run(root, monkeypatch, fake) == 0
    offered = {c["id"] for c in seen["pack"]["free_agents"]}
    assert offered == {"fa_qb"}   # not rostered, not hurt, not already kicked


def test_a_signing_swaps_the_starter_and_conserves_the_roster(tmp_path, monkeypatch):
    root, _, fake = _league(tmp_path, {"add": "fa_qb", "drop": "b5",
                                       "start_slot": "QB", "reasoning": "go"})
    assert _run(root, monkeypatch, fake) == 0
    r = json.loads((root / "teams" / "me" / "roster.json").read_text())
    assert r["starters"]["QB"] == "fa_qb"
    assert "qb1" in r["bench"] and "b5" not in r["bench"]
    tx = (root / "state" / "transactions.jsonl").read_text()
    assert '"action": "free_agent"' in tx and '"bid": 0' in tx


def test_a_player_who_was_not_offered_is_refused(tmp_path, monkeypatch):
    root, _, fake = _league(tmp_path, {"add": "taken_qb", "drop": "b5",
                                       "start_slot": "QB", "reasoning": "steal"})
    assert _run(root, monkeypatch, fake) == 2
    r = json.loads((root / "teams" / "me" / "roster.json").read_text())
    assert r["starters"]["QB"] == "qb1"   # untouched


# ---- commissioner review: nothing applies until it approves -------------

SIGN = {"add": "fa_qb", "drop": "b5", "start_slot": "QB", "reasoning": "go"}


def _roster(root):
    return json.loads((root / "teams" / "me" / "roster.json").read_text())


def _log(root):
    return json.loads((root / "state" / "weeks" / "2026-w05" / "decisions"
                       / "me.free-agency.json").read_text())


def test_the_commissioner_sees_the_exact_move_before_it_applies(tmp_path, monkeypatch):
    root, seen, fake = _league(tmp_path, SIGN)
    assert _run(root, monkeypatch, fake) == 0
    pack = seen["review_pack"]
    assert pack["decision"] == SIGN
    assert pack["roster_after"]["starters"]["QB"] == "fa_qb"
    assert pack["roster_before"]["starters"]["QB"] == "qb1"
    assert _log(root)[-1]["outcome"] == "applied"
    assert _log(root)[-1]["review"]["verdict"] == "approve"


def test_a_block_applies_nothing_and_is_logged(tmp_path, monkeypatch):
    root, _, fake = _league(tmp_path, SIGN, verdict="block")
    assert _run(root, monkeypatch, fake) == 4
    assert _roster(root)["starters"]["QB"] == "qb1"       # untouched
    assert _log(root)[-1]["outcome"] == "blocked"
    tx = (root / "state" / "transactions.jsonl").read_text()
    assert '"status": "rejected"' in tx


def test_no_review_means_no_move(tmp_path, monkeypatch):
    """Fails closed: a move the office could not review is one it did not approve."""
    root, _, fake = _league(tmp_path, SIGN, verdict="error")
    assert _run(root, monkeypatch, fake) == 3
    assert _roster(root)["starters"]["QB"] == "qb1"
    assert not (root / "state" / "transactions.jsonl").exists()
    assert _log(root)[-1]["outcome"] == "review_failed"


def test_standing_pat_needs_no_review(tmp_path, monkeypatch):
    root, seen, fake = _league(tmp_path, {"add": None, "drop": None,
                                          "start_slot": None, "reasoning": "no"})
    assert _run(root, monkeypatch, fake) == 0
    assert "review_pack" not in seen


def test_an_older_single_entry_log_is_kept_not_overwritten(tmp_path, monkeypatch):
    root, _, fake = _league(tmp_path, SIGN)
    d = root / "state" / "weeks" / "2026-w05" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / "me.free-agency.json").write_text(json.dumps({"add": "earlier"}))
    assert _run(root, monkeypatch, fake) == 0
    log = _log(root)
    assert log[0] == {"add": "earlier"} and log[-1]["outcome"] == "applied"

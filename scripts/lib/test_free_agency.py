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


def _league(tmp_path, gm_reply):
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
    seen = {}

    def fake_turn(**kw):
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

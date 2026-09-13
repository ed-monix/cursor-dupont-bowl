"""Tests for the harness-side trade pre-validation gate. No network."""

import json
from pathlib import Path

from lib.trades import collect_offers, screen_offers, validate_offer

PLAYERS = {
    "p1": {"name": "One", "pos": "RB", "team": "AAA", "status": "ACT", "injury": None},
    "p2": {"name": "Two", "pos": "WR", "team": "BBB", "status": "ACT", "injury": None},
    "p3": {"name": "Three", "pos": "TE", "team": "CCC", "status": "ACT", "injury": None},
    "p4": {"name": "Four", "pos": "QB", "team": "DDD", "status": "ACT", "injury": None},
}


def _roster(team, bench):
    return {
        "team": team, "faab_remaining": 100,
        "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None,
                     "WR2": None, "TE": None, "FLEX": None, "K": None, "DEF": None},
        "bench": list(bench), "ir": [],
    }


def _write_decision(d: Path, slug: str, **fields):
    base = {"claims": [], "drops": [], "note_reply": ""}
    base.update(fields)
    (d / f"{slug}.json").write_text(json.dumps(base), encoding="utf-8")


# ---- collect_offers ----

def test_collect_offers_only_from_real_decision_files_with_offer(tmp_path: Path):
    d = tmp_path / "decisions"
    d.mkdir()
    _write_decision(d, "alpha", trade_offer={"to_team": "bravo", "out": ["p1"], "in": ["p2"]})
    _write_decision(d, "bravo")  # no trade_offer at all
    (d / "alpha.lineup-early.json").write_text(json.dumps({"starters": {}}), encoding="utf-8")
    (d / "alpha.trade.json").write_text(json.dumps({"response": "accept"}), encoding="utf-8")

    offers = collect_offers(d)
    assert list(offers) == ["alpha"]
    assert offers["alpha"]["to_team"] == "bravo"


def test_collect_offers_skips_malformed_file(tmp_path: Path):
    d = tmp_path / "decisions"
    d.mkdir()
    _write_decision(d, "alpha", trade_offer={"to_team": "bravo", "out": ["p1"], "in": ["p2"]})
    (d / "broken.json").write_text("{", encoding="utf-8")

    offers = collect_offers(d)
    assert list(offers) == ["alpha"]


def test_collect_offers_empty_dir(tmp_path: Path):
    assert collect_offers(tmp_path / "nope") == {}


# ---- validate_offer ----

def test_validate_offer_legal_swap_passes():
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p1"], "in": ["p2"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is True
    assert reason == ""


def test_validate_offer_rejects_player_offerer_does_not_hold():
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p3"], "in": ["p2"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "p3" in reason


def test_validate_offer_rejects_player_target_does_not_hold():
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p1"], "in": ["p4"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "p4" in reason


def test_validate_offer_rejects_self_trade():
    rosters = {"alpha": _roster("alpha", ["p1"])}
    offer = {"to_team": "alpha", "out": ["p1"], "in": ["p1"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "yourself" in reason


def test_validate_offer_rejects_unknown_to_team():
    rosters = {"alpha": _roster("alpha", ["p1"])}
    offer = {"to_team": "ghost", "out": ["p1"], "in": ["p2"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "ghost" in reason


def test_validate_offer_rejects_overflowed_bench_with_apply_transaction_message():
    roster_config = {
        "starters": {"QB": ["QB"]},
        "bench_slots": 1,
        "ir_slots": 1,
    }
    alpha = {"team": "alpha", "faab_remaining": 100,
             "starters": {"QB": None}, "bench": ["p1"], "ir": []}
    bravo = {"team": "bravo", "faab_remaining": 100,
             "starters": {"QB": None}, "bench": ["p2", "p3"], "ir": []}
    rosters = {"alpha": alpha, "bravo": bravo}
    # bravo gives up both p2 and p3 for alpha's single p1 -> alpha's bench
    # would grow from 1 to 2, over its 1-slot limit.
    offer = {"to_team": "bravo", "out": ["p1"], "in": ["p2", "p3"]}
    ok, reason = validate_offer("alpha", offer, rosters, PLAYERS, roster_config)
    assert ok is False
    assert "bench" in reason.lower()


# ---- screen_offers ----

def _week_dir(root: Path, season="2026", week=5) -> Path:
    d = root / "state" / "weeks" / f"{season}-w{week:02d}" / "decisions"
    d.mkdir(parents=True)
    return d


def test_screen_offers_legal_offer_ok(tmp_path: Path):
    d = _week_dir(tmp_path, week=5)
    _write_decision(d, "alpha", trade_offer={"to_team": "bravo", "out": ["p1"], "in": ["p2"]})
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}

    records = screen_offers(tmp_path, "2026", 5, rosters=rosters, players=PLAYERS)
    assert len(records) == 1
    assert records[0]["from"] == "alpha"
    assert records[0]["ok"] is True


def test_screen_offers_week_11_allowed_week_12_rejected(tmp_path: Path):
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p1"], "in": ["p2"]}

    d11 = _week_dir(tmp_path, week=11)
    _write_decision(d11, "alpha", trade_offer=offer)
    records11 = screen_offers(tmp_path, "2026", 11, rosters=rosters, players=PLAYERS)
    assert records11[0]["ok"] is True

    root12 = tmp_path / "w12root"
    d12 = _week_dir(root12, week=12)
    _write_decision(d12, "alpha", trade_offer=offer)
    records12 = screen_offers(root12, "2026", 12, rosters=rosters, players=PLAYERS)
    assert records12[0]["ok"] is False
    assert "deadline" in records12[0]["reason"].lower()


def test_screen_offers_rejects_two_offers_from_one_team(tmp_path: Path, monkeypatch):
    """Belt-and-braces check: a decision file can only carry one trade_offer
    per the schema, so screen_offers can only see a duplicate outgoing offer
    if something upstream of collect_offers hands it one. Simulate that by
    patching collect_offers to return a dict whose .items() repeats a key --
    exactly the shape screen_offers iterates over."""
    d = _week_dir(tmp_path, week=5)
    _write_decision(d, "alpha", trade_offer={"to_team": "bravo", "out": ["p1"], "in": ["p2"]})
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}

    import lib.trades as trades_mod

    original_collect_offers = trades_mod.collect_offers

    class DupDict(dict):
        def items(self):
            base = list(super().items())
            return base + base

    monkeypatch.setattr(trades_mod, "collect_offers",
                         lambda decisions_dir: DupDict(original_collect_offers(decisions_dir)))

    records = screen_offers(tmp_path, "2026", 5, rosters=rosters, players=PLAYERS)
    assert len(records) == 2
    assert records[0]["ok"] is True
    assert records[1]["ok"] is False
    assert "already has an outgoing offer" in records[1]["reason"]

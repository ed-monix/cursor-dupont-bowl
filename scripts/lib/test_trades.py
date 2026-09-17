"""Tests for the harness-side trade pre-validation gate. No network."""

import json
from pathlib import Path

from lib.trades import (apply_accepted, collect_offers, screen_offers,
                        validate_offer)

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
    assert [o["to_team"] for o in offers["alpha"]] == ["bravo"]


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
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is True
    assert reason == ""


def test_validate_offer_rejects_player_offerer_does_not_hold():
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p3"], "in": ["p2"]}
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "p3" in reason


def test_validate_offer_rejects_player_target_does_not_hold():
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    offer = {"to_team": "bravo", "out": ["p1"], "in": ["p4"]}
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "p4" in reason


def test_validate_offer_rejects_self_trade():
    rosters = {"alpha": _roster("alpha", ["p1"])}
    offer = {"to_team": "alpha", "out": ["p1"], "in": ["p1"]}
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS)
    assert ok is False
    assert "yourself" in reason


def test_validate_offer_rejects_unknown_to_team():
    rosters = {"alpha": _roster("alpha", ["p1"])}
    offer = {"to_team": "ghost", "out": ["p1"], "in": ["p2"]}
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS)
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
    ok, reason, _drops = validate_offer("alpha", offer, rosters, PLAYERS, roster_config)
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


def test_a_team_may_make_several_offers_now(tmp_path: Path):
    """One offer a week made the market nearly inert: a GM got a single shot,
    and when the target said no -- both of week 2's did -- that was the whole
    week. Three is a market."""
    d = _week_dir(tmp_path, week=5)
    _write_decision(d, "alpha", trade_offers=[
        {"to_team": "bravo", "out": ["p1"], "in": ["p2"]},
        {"to_team": "bravo", "out": ["p1"], "in": ["p3"]},
    ])
    rosters = {"alpha": _roster("alpha", ["p1"]),
               "bravo": _roster("bravo", ["p2", "p3"])}

    records = screen_offers(tmp_path, "2026", 5, rosters=rosters, players=PLAYERS)
    assert len(records) == 2
    assert all(r["ok"] for r in records), [r["reason"] for r in records]


def test_offers_past_the_cap_are_refused_in_submission_order(tmp_path: Path):
    """A GM that writes four keeps its first three, rather than losing all."""
    d = _week_dir(tmp_path, week=5)
    _write_decision(d, "alpha", trade_offers=[
        {"to_team": "bravo", "out": ["p1"], "in": ["p2"]},
        {"to_team": "bravo", "out": ["p1"], "in": ["p3"]},
        {"to_team": "bravo", "out": ["p1"], "in": ["p4"]},
        {"to_team": "bravo", "out": ["p1"], "in": ["p2"]},
    ])
    rosters = {"alpha": _roster("alpha", ["p1"]),
               "bravo": _roster("bravo", ["p2", "p3", "p4"])}

    records = screen_offers(tmp_path, "2026", 5, rosters=rosters, players=PLAYERS)
    assert len(records) == 4
    assert [r["ok"] for r in records] == [True, True, True, False]
    assert "at most 3 offers" in records[3]["reason"]


def test_the_old_single_offer_key_still_works(tmp_path: Path):
    """Older decision files, and any GM still writing `trade_offer`."""
    d = _week_dir(tmp_path, week=5)
    _write_decision(d, "alpha", trade_offer={"to_team": "bravo",
                                             "out": ["p1"], "in": ["p2"]})
    rosters = {"alpha": _roster("alpha", ["p1"]), "bravo": _roster("bravo", ["p2"])}
    records = screen_offers(tmp_path, "2026", 5, rosters=rosters, players=PLAYERS)
    assert len(records) == 1 and records[0]["ok"]


# --------------------------------------------------------------------------
# Applying what a target accepted. Before apply_accepted existed, a GM could
# say yes and nothing happened: the response sat in <slug>.trade.json,
# collect_waiver_claims skipped it by name, and no roster ever moved.
# --------------------------------------------------------------------------

def _traded_league(tmp_path: Path):
    """Two teams with LEGAL rosters, one screened offer, ready for a response.

    apply_transaction validates the whole resulting roster, so a fixture with
    empty starters fails on slot requirements rather than on the trade.
    """
    from lib import trades as trades_mod

    slots = [("QB", "QB"), ("RB1", "RB"), ("RB2", "RB"), ("WR1", "WR"),
             ("WR2", "WR"), ("TE", "TE"), ("FLEX", "RB"), ("K", "K"),
             ("DEF", "DEF")]
    players = {}
    for slug, spare in (("alpha", "a1"), ("bravo", "b1")):
        starters = {}
        for slot, pos in slots:
            pid = f"{slug}-{slot}"
            starters[slot] = pid  # rosters store bare ids, not dicts
            players[pid] = {"id": pid, "name": pid, "pos": pos}
        players[spare] = {"id": spare, "name": spare, "pos": "WR"}
        (tmp_path / "teams" / slug).mkdir(parents=True)
        (tmp_path / "teams" / slug / "roster.json").write_text(json.dumps({
            "team": slug, "starters": starters,
            "bench": [spare],
            "ir": [], "faab_remaining": 100,
        }), encoding="utf-8")

    wdir = tmp_path / "state" / "weeks" / "2026-w05"
    (wdir / "decisions").mkdir(parents=True)
    (wdir / "trade-screen.json").write_text(json.dumps([{
        "from": "alpha", "ok": True, "reason": "",
        "offer": {"to_team": "bravo", "out": ["a1"], "in": ["b1"]},
    }]), encoding="utf-8")
    (tmp_path / "state" / "players.json").write_text(json.dumps(players),
                                                     encoding="utf-8")
    return wdir, trades_mod


def test_accepted_trade_moves_both_rosters_and_is_logged(tmp_path: Path):
    wdir, trades_mod = _traded_league(tmp_path)
    (wdir / "decisions" / "bravo.trade.json").write_text(
        json.dumps({"response": "accept", "message": "Fine."}), encoding="utf-8")

    results = trades_mod.apply_accepted(tmp_path, "2026", 5)
    assert [r["applied"] for r in results] == [True]

    alpha = json.loads((tmp_path / "teams" / "alpha" / "roster.json").read_text())
    bravo = json.loads((tmp_path / "teams" / "bravo" / "roster.json").read_text())
    assert "b1" in json.dumps(alpha) and "a1" not in json.dumps(alpha)
    assert "a1" in json.dumps(bravo) and "b1" not in json.dumps(bravo)

    logged = [json.loads(l) for l in
              (tmp_path / "state" / "transactions.jsonl").read_text().splitlines()]
    assert {e["team"] for e in logged} == {"alpha", "bravo"}
    assert all(e["action"] == "trade" and e["status"] == "applied" for e in logged)


def test_rejected_trade_changes_nothing(tmp_path: Path):
    wdir, trades_mod = _traded_league(tmp_path)
    (wdir / "decisions" / "bravo.trade.json").write_text(
        json.dumps({"response": "reject"}), encoding="utf-8")

    results = trades_mod.apply_accepted(tmp_path, "2026", 5)
    assert results[0]["applied"] is False
    alpha = json.loads((tmp_path / "teams" / "alpha" / "roster.json").read_text())
    assert "a1" in json.dumps(alpha)
    assert not (tmp_path / "state" / "transactions.jsonl").exists()


def test_counter_is_recorded_never_auto_applied(tmp_path: Path):
    """Chasing a counter automatically is an unbounded negotiation."""
    wdir, trades_mod = _traded_league(tmp_path)
    (wdir / "decisions" / "bravo.trade.json").write_text(json.dumps({
        "response": "counter",
        "counter": {"to_team": "alpha", "out": ["b1"], "in": ["a1"]},
    }), encoding="utf-8")

    results = trades_mod.apply_accepted(tmp_path, "2026", 5)
    assert results[0]["applied"] is False
    assert "counter" in results[0]["reason"]
    assert not (tmp_path / "state" / "transactions.jsonl").exists()


def test_response_with_no_screened_offer_is_ignored(tmp_path: Path):
    wdir, trades_mod = _traded_league(tmp_path)
    (wdir / "decisions" / "ghost.trade.json").write_text(
        json.dumps({"response": "accept"}), encoding="utf-8")

    results = trades_mod.apply_accepted(tmp_path, "2026", 5)
    ghost = [r for r in results if r["target"] == "ghost"][0]
    assert ghost["applied"] is False
    assert "no screened offer" in ghost["reason"]


def test_dry_run_reports_without_writing(tmp_path: Path):
    wdir, trades_mod = _traded_league(tmp_path)
    (wdir / "decisions" / "bravo.trade.json").write_text(
        json.dumps({"response": "accept"}), encoding="utf-8")

    results = trades_mod.apply_accepted(tmp_path, "2026", 5, dry_run=True)
    assert results[0]["applied"] is True
    alpha = json.loads((tmp_path / "teams" / "alpha" / "roster.json").read_text())
    assert "a1" in json.dumps(alpha)  # untouched on disk
    assert not (tmp_path / "state" / "transactions.jsonl").exists()


# ---- uneven trades: a full roster makes room, it does not refuse -----------
#
# Every team carries a full 15 and validate_offer used to require both sides
# legal the instant the swap landed. That made every 2-for-1 illegal on arrival:
# week 2 screened out both offers in the league on exactly this, including one
# an owner had asked their GM to make. An uneven trade is normal; the receiving
# side just has to cut someone.

SLOT_POS = {"QB": "QB", "RB1": "RB", "RB2": "RB", "WR1": "WR", "WR2": "WR",
            "TE": "TE", "FLEX": "RB", "K": "K", "DEF": "DEF"}
CONFIG = {"bench_slots": 6, "ir_slots": 1}


def _full(team):
    """9 legal starters + a full 6-man bench = the 15 every team here carries."""
    return {
        "team": team, "faab_remaining": 100,
        "starters": {slot: f"{team}-{slot}" for slot in SLOT_POS},
        "bench": [f"{team}-b{i}" for i in range(6)], "ir": [],
    }


def _full_players():
    out = {}
    for team in ("alpha", "bravo"):
        for slot, pos in SLOT_POS.items():
            out[f"{team}-{slot}"] = {"name": slot, "pos": pos, "team": "AAA",
                                     "status": "ACT", "injury": None}
        for i in range(6):
            out[f"{team}-b{i}"] = {"name": f"b{i}", "pos": "RB", "team": "AAA",
                                   "status": "ACT", "injury": None}
    return out


def test_two_for_one_is_legal_and_costs_the_receiver_a_drop():
    rosters = {"alpha": _full("alpha"), "bravo": _full("bravo")}
    offer = {"to_team": "bravo", "out": ["alpha-b0", "alpha-b1"], "in": ["bravo-b0"]}
    ok, reason, needs = validate_offer("alpha", offer, rosters,
                                       _full_players(), CONFIG)
    assert ok, reason
    assert needs == {"bravo": 1}          # bravo nets +1 and is full
    assert "alpha" not in needs           # alpha nets -1, owes nothing


def test_even_trade_costs_nobody_a_drop():
    rosters = {"alpha": _full("alpha"), "bravo": _full("bravo")}
    offer = {"to_team": "bravo", "out": ["alpha-b0"], "in": ["bravo-b0"]}
    ok, reason, needs = validate_offer("alpha", offer, rosters,
                                       _full_players(), CONFIG)
    assert ok, reason
    assert needs is None


def test_three_for_one_asks_the_receiver_for_two():
    rosters = {"alpha": _full("alpha"), "bravo": _full("bravo")}
    offer = {"to_team": "bravo",
             "out": ["alpha-b0", "alpha-b1", "alpha-b2"], "in": ["bravo-b0"]}
    ok, reason, needs = validate_offer("alpha", offer, rosters,
                                       _full_players(), CONFIG)
    assert ok, reason
    assert needs == {"bravo": 2}


def test_offerer_taking_back_more_must_name_its_own_drop():
    """The offerer knew it was net-positive, so it names the casualty up front."""
    rosters = {"alpha": _full("alpha"), "bravo": _full("bravo")}
    offer = {"to_team": "bravo", "out": ["alpha-b0"],
             "in": ["bravo-b0", "bravo-b1"]}
    ok, reason, _ = validate_offer("alpha", offer, rosters, _full_players(), CONFIG)
    assert not ok
    assert "names only 0 drop" in reason

    offer["drop"] = ["alpha-b5"]
    ok, reason, needs = validate_offer("alpha", offer, rosters,
                                       _full_players(), CONFIG)
    assert ok, reason
    assert needs == {"alpha": 1}


def test_a_player_in_the_trade_is_never_counted_as_droppable():
    """Accepting a player only to waive him is not making room."""
    from lib.trades import droppable_for
    can = droppable_for(_full("alpha"), ["alpha-b0"], ["bravo-b0"])
    assert "alpha-b0" not in can   # already leaving
    assert "bravo-b0" not in can   # just arrived


def test_drops_needed_asks_the_validator_how_many():
    from lib.trades import drops_needed
    r, P = _full("alpha"), _full_players()
    assert drops_needed(r, ["alpha-b0"], ["bravo-b0"], P, CONFIG) == 0
    assert drops_needed(r, ["alpha-b0"], ["bravo-b0", "bravo-b1"], P, CONFIG) == 1
    assert drops_needed(r, ["alpha-b0", "alpha-b1"], ["bravo-b0"], P, CONFIG) == 0


def test_trading_away_a_starter_still_costs_a_bench_spot():
    """The case the old arithmetic got wrong, and that killed the real offers.

    kardashian was asked for Justin Jefferson, a STARTER, in a 2-for-1. Giving
    him up empties a lineup slot; both incoming players still land on the bench,
    which was already full. Total roster size said "fits". The bench said no.
    """
    from lib.trades import drops_needed
    r, P = _full("alpha"), _full_players()
    # give up a starter, take back two: bench grows by two, frees nothing
    assert drops_needed(r, ["alpha-QB"], ["bravo-b0", "bravo-b1"], P, CONFIG) == 2


# ---- several accepts, and who decides between them ------------------------
#
# A team may send three offers now, so three yeses can come back at once. If
# they all fit, all of them stand. If they cannot — the same player promised to
# two teams — the OFFERING GM picks. The harness applying the first and voiding
# the rest by screening order would be the harness deciding a trade.

def _mini_players():
    return {pid: {"name": pid, "pos": "RB", "team": "AAA",
                  "status": "Active", "injury": None}
            for pid in ("a1", "a2", "b1", "c1")}


def _mini_roster(team, bench):
    return {"team": team, "faab_remaining": 100,
            "starters": {"QB": None, "RB1": None, "RB2": None, "WR1": None,
                         "WR2": None, "TE": None, "FLEX": None, "K": None,
                         "DEF": None},
            "bench": list(bench), "ir": []}


def _stage(tmp_path, screen, responses):
    """Write a trade-screen and the matching .trade.json response files."""
    w = tmp_path / "state" / "weeks" / "2026-w05"
    (w / "decisions").mkdir(parents=True)
    (w / "trade-screen.json").write_text(json.dumps(screen), encoding="utf-8")
    for target, payload in responses.items():
        (w / "decisions" / f"{target}.trade.json").write_text(
            json.dumps(payload), encoding="utf-8")
    for team, bench in (("alpha", ["a1", "a2"]), ("bravo", ["b1"]),
                        ("charlie", ["c1"])):
        d = tmp_path / "teams" / team
        d.mkdir(parents=True)
        (d / "roster.json").write_text(json.dumps(_mini_roster(team, bench)),
                                       encoding="utf-8")
    (tmp_path / "state" / "players.json").write_text(
        json.dumps(_mini_players()), encoding="utf-8")


def test_two_accepts_that_fit_are_both_honoured(tmp_path: Path):
    """Three offers for three different players, three yeses: a good week."""
    screen = [
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "bravo", "out": ["a1"], "in": ["b1"]}},
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "charlie", "out": ["a2"], "in": ["c1"]}},
    ]
    _stage(tmp_path, screen, {
        "bravo": {"responses": [{"from": "alpha", "response": "accept"}]},
        "charlie": {"responses": [{"from": "alpha", "response": "accept"}]},
    })
    results = apply_accepted(tmp_path, "2026", 5, dry_run=True)
    assert [r["applied"] for r in results] == [True, True], results


def test_the_same_player_promised_twice_is_a_conflict_the_offerer_settles(tmp_path):
    """alpha offered a1 to both bravo and charlie. Both said yes."""
    screen = [
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "bravo", "out": ["a1"], "in": ["b1"]}},
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "charlie", "out": ["a1"], "in": ["c1"]}},
    ]
    _stage(tmp_path, screen, {
        "bravo": {"responses": [{"from": "alpha", "response": "accept"}]},
        "charlie": {"responses": [{"from": "alpha", "response": "accept"}]},
    })

    asked = {}

    def choose(offerer, cands):
        asked["offerer"] = offerer
        asked["n"] = len(cands)
        # the GM wants charlie's deal
        return [c for c in cands if c["target"] == "charlie"]

    results = apply_accepted(tmp_path, "2026", 5, dry_run=True, choose=choose)
    assert asked == {"offerer": "alpha", "n": 2}
    applied = [r for r in results if r["applied"]]
    declined = [r for r in results if not r["applied"]]
    assert [r["target"] for r in applied] == ["charlie"]
    assert [r["target"] for r in declined] == ["bravo"]
    assert "chose to honour instead" in declined[0]["reason"]


def test_a_conflict_without_a_chooser_keeps_what_fits_and_reports_the_rest(tmp_path):
    screen = [
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "bravo", "out": ["a1"], "in": ["b1"]}},
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "charlie", "out": ["a1"], "in": ["c1"]}},
    ]
    _stage(tmp_path, screen, {
        "bravo": {"responses": [{"from": "alpha", "response": "accept"}]},
        "charlie": {"responses": [{"from": "alpha", "response": "accept"}]},
    })
    results = apply_accepted(tmp_path, "2026", 5, dry_run=True)
    assert sum(1 for r in results if r["applied"]) == 1
    assert sum(1 for r in results if not r["applied"]) == 1


def test_each_answer_is_matched_to_the_offer_it_names(tmp_path: Path):
    """bravo is sent two offers by two teams and answers each differently."""
    screen = [
        {"from": "alpha", "ok": True,
         "offer": {"to_team": "bravo", "out": ["a1"], "in": ["b1"]}},
        {"from": "charlie", "ok": True,
         "offer": {"to_team": "bravo", "out": ["c1"], "in": ["b1"]}},
    ]
    _stage(tmp_path, screen, {
        "bravo": {"responses": [
            {"from": "alpha", "response": "reject"},
            {"from": "charlie", "response": "accept"},
        ]},
    })
    results = apply_accepted(tmp_path, "2026", 5, dry_run=True)
    by_from = {r["from"]: r for r in results}
    assert by_from["alpha"]["applied"] is False
    assert by_from["charlie"]["applied"] is True

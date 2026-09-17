"""Tests for scripts/lib/rosters.py. Pure, no network, no external files."""

import copy

import pytest

from lib.rosters import (
    apply_transaction,
    best_legal_lineup,
    injury_bars_starting,
    duplicate_players_across_teams,
    roster_config_from_league,
    slot_position_ok,
    validate_lineup,
    validate_roster,
)


def make_players(**overrides):
    """Small inline players fixture: id -> {"pos": ..., "name": ...}.

    Ships with p_qb1/p_rb1/p_rb2/p_wr1/p_wr2/p_te1/p_k1/p_def1 plus enough
    spares (p_rb3, p_wr3, p_te2, p_flex_extra) to build bench/trade cases;
    pass overrides to add more.
    """
    base = {
        "p_qb1": {"name": "QB One", "pos": "QB", "team": "AAA", "status": "Active", "injury": None},
        "p_rb1": {"name": "RB One", "pos": "RB", "team": "AAA", "status": "Active", "injury": None},
        "p_rb2": {"name": "RB Two", "pos": "RB", "team": "AAA", "status": "Active", "injury": None},
        "p_rb3": {"name": "RB Three", "pos": "RB", "team": "AAA", "status": "Active", "injury": None},
        "p_wr1": {"name": "WR One", "pos": "WR", "team": "AAA", "status": "Active", "injury": None},
        "p_wr2": {"name": "WR Two", "pos": "WR", "team": "AAA", "status": "Active", "injury": None},
        "p_wr3": {"name": "WR Three", "pos": "WR", "team": "AAA", "status": "Active", "injury": None},
        "p_te1": {"name": "TE One", "pos": "TE", "team": "AAA", "status": "Active", "injury": None},
        "p_te2": {"name": "TE Two", "pos": "TE", "team": "AAA", "status": "Active", "injury": None},
        "p_k1": {"name": "K One", "pos": "K", "team": "AAA", "status": "Active", "injury": None},
        "p_def1": {"name": "DEF One", "pos": "DEF", "team": "AAA", "status": "Active", "injury": None},
    }
    base.update(overrides)
    return base


def make_roster(team="team-a", starters=None, bench=None, ir=None, faab=100):
    default_starters = {
        "QB": "p_qb1", "RB1": "p_rb1", "RB2": "p_rb2",
        "WR1": "p_wr1", "WR2": "p_wr2", "TE": "p_te1",
        "FLEX": "p_rb3", "K": "p_k1", "DEF": "p_def1",
    }
    if starters is not None:
        default_starters.update(starters)
    return {
        "team": team,
        "faab_remaining": faab,
        "starters": default_starters,
        "bench": bench if bench is not None else [],
        "ir": ir if ir is not None else [],
    }


# --- AC: FLEX accepts RB/WR/TE but not QB -----------------------------------

def test_flex_accepts_rb_wr_te():
    assert slot_position_ok("FLEX", "RB") is True
    assert slot_position_ok("FLEX", "WR") is True
    assert slot_position_ok("FLEX", "TE") is True


def test_flex_rejects_qb_and_other_non_flex_positions():
    assert slot_position_ok("FLEX", "QB") is False
    assert slot_position_ok("FLEX", "K") is False
    assert slot_position_ok("FLEX", "DEF") is False


def test_non_flex_slots_are_strict():
    assert slot_position_ok("QB", "QB") is True
    assert slot_position_ok("QB", "RB") is False
    assert slot_position_ok("K", "K") is True
    assert slot_position_ok("DEF", "DEF") is True


# --- AC: duplicate player across two teams rejected --------------------------

def test_duplicate_player_across_teams_detected():
    team_a = make_roster(team="team-a")
    team_b = make_roster(team="team-b", starters={"QB": "p_rb1"})  # p_rb1 double-rostered
    dupes = duplicate_players_across_teams([team_a, team_b])
    assert "p_rb1" in dupes


def test_no_duplicates_when_rosters_disjoint():
    team_a = make_roster(team="team-a")
    team_b = make_roster(team="team-b", starters={
        "QB": "other_qb", "RB1": "other_rb1", "RB2": "other_rb2",
        "WR1": "other_wr1", "WR2": "other_wr2", "TE": "other_te",
        "FLEX": "other_flex", "K": "other_k", "DEF": "other_def",
    })
    assert duplicate_players_across_teams([team_a, team_b]) == []


# --- AC: trade that would overflow a bench is rejected -----------------------

def test_trade_overflow_bench_rejected_and_original_untouched():
    players = make_players()
    roster = make_roster(bench=["b1", "b2", "b3", "b4", "b5", "b6"])  # bench already full (6)
    original = copy.deepcopy(roster)

    txn = {"type": "trade", "out": [], "in": ["p_te2"]}  # would push bench to 7
    with pytest.raises(ValueError):
        apply_transaction(roster, txn, players)

    assert roster == original  # input never partially applied


def test_trade_within_bench_limit_succeeds():
    players = make_players()
    roster = make_roster(bench=["b1", "b2"])
    txn = {"type": "trade", "out": ["b1"], "in": ["p_te2"]}
    new_roster = apply_transaction(roster, txn, players)
    assert "b1" not in new_roster["bench"]
    assert "p_te2" in new_roster["bench"]
    # original untouched
    assert roster["bench"] == ["b1", "b2"]


# --- plus: fully-legal roster validates ok ------------------------------------

def test_fully_legal_roster_validates_ok():
    players = make_players()
    roster = make_roster()
    ok, errors = validate_roster(roster, players)
    assert ok is True
    assert errors == []


# --- plus: faab_remaining < 0 fails -------------------------------------------

def test_negative_faab_fails_validation():
    players = make_players()
    roster = make_roster(faab=-5)
    ok, errors = validate_roster(roster, players)
    assert ok is False
    assert any("faab_remaining" in e for e in errors)


# --- plus: validate_lineup fails when a starter slot is null -----------------

def test_lineup_fails_on_empty_starter_slot():
    players = make_players()
    roster = make_roster(starters={"K": None})
    ok, errors = validate_lineup(roster, players)
    assert ok is False
    assert any("slot K is empty" in e for e in errors)


def test_lineup_ok_when_fully_filled_and_legal():
    players = make_players()
    roster = make_roster()
    ok, errors = validate_lineup(roster, players)
    assert ok is True
    assert errors == []


def test_lineup_fails_when_same_player_started_twice():
    players = make_players()
    roster = make_roster(starters={"FLEX": "p_rb1"})  # p_rb1 already RB1
    ok, errors = validate_lineup(roster, players)
    assert ok is False
    assert any("multiple slots" in e for e in errors)


# --- extra apply_transaction coverage -----------------------------------------

def test_apply_transaction_add_with_drop_happy_path():
    players = make_players()
    roster = make_roster(bench=["bench_wr"])
    txn = {"type": "add", "player": "new_rb", "to": "bench", "drop": "bench_wr"}
    new_roster = apply_transaction(roster, txn, players)
    assert new_roster["bench"] == ["new_rb"]
    # original untouched
    assert roster["bench"] == ["bench_wr"]


def test_apply_transaction_drop_unknown_player_raises():
    players = make_players()
    roster = make_roster()
    original = copy.deepcopy(roster)
    with pytest.raises(ValueError):
        apply_transaction(roster, {"type": "drop", "player": "nobody"}, players)
    assert roster == original


def test_apply_transaction_add_into_occupied_slot_without_drop_raises():
    players = make_players()
    roster = make_roster()
    original = copy.deepcopy(roster)
    txn = {"type": "add", "player": "p_te2", "to": "TE"}  # TE already has p_te1
    with pytest.raises(ValueError):
        apply_transaction(roster, txn, players)
    assert roster == original


def test_apply_transaction_rejects_position_ineligible_starter_slot():
    players = make_players()
    roster = make_roster(starters={"K": None})
    original = copy.deepcopy(roster)
    txn = {"type": "add", "player": "p_wr3", "to": "K"}  # WR into K slot
    with pytest.raises(ValueError):
        apply_transaction(roster, txn, players)
    assert roster == original


# --- AC (3.3): best_legal_lineup -- deterministic Sunday fallback ------------

# Simple, single-key scoring so a projected stat line's point value is
# transparent in every test below: {"proj_pts": N} scores as exactly N.
SIMPLE_SCORING = {"proj_pts": 1.0}


def _lineup_fixture():
    """Players/roster/projections for a pool with a clear best at every
    position, so the expected optimal lineup (including FLEX) is obvious.
    """
    players = make_players()
    roster = make_roster(bench=["p_wr3", "p_te2"])  # rest of default starters, see make_roster()

    projections = {
        "p_qb1": {"proj_pts": 20},
        "p_rb1": {"proj_pts": 15},  # best RB -> RB1
        "p_rb2": {"proj_pts": 12},  # 2nd best RB -> RB2
        "p_rb3": {"proj_pts": 6},   # 3rd RB, leftover FLEX candidate
        "p_wr1": {"proj_pts": 14},  # best WR -> WR1
        "p_wr2": {"proj_pts": 11},  # 2nd best WR -> WR2
        "p_wr3": {"proj_pts": 8},   # 3rd WR, leftover FLEX candidate (bench)
        "p_te1": {"proj_pts": 9},   # best TE -> TE
        "p_te2": {"proj_pts": 3},   # 2nd TE, leftover FLEX candidate (bench)
        "p_k1": {"proj_pts": 5},
        "p_def1": {"proj_pts": 7},
    }
    return players, roster, projections


def test_best_legal_lineup_optimal_at_every_slot_and_flex_takes_best_leftover():
    players, roster, projections = _lineup_fixture()

    result = best_legal_lineup(roster, players, projections, SIMPLE_SCORING)

    starters = result["starters"]
    assert starters["QB"] == "p_qb1"
    assert starters["RB1"] == "p_rb1"
    assert starters["RB2"] == "p_rb2"
    assert starters["WR1"] == "p_wr1"
    assert starters["WR2"] == "p_wr2"
    assert starters["TE"] == "p_te1"
    assert starters["K"] == "p_k1"
    assert starters["DEF"] == "p_def1"

    # FLEX: once RB1/RB2 (p_rb1, p_rb2), WR1/WR2 (p_wr1, p_wr2) and TE
    # (p_te1) are taken, the only RB/WR/TE left in the pool are
    # p_rb3 (6 pts), p_wr3 (8 pts) and p_te2 (3 pts). p_wr3 has the
    # highest projection of that leftover group, so FLEX must be p_wr3
    # -- not p_rb3 (higher position priority doesn't matter, points do)
    # and not p_te2 (a worse leftover than either).
    assert starters["FLEX"] == "p_wr3"

    # everyone not started lands on the bench; original roster untouched
    assert set(result["bench"]) == {"p_rb3", "p_te2"}
    assert roster["bench"] == ["p_wr3", "p_te2"]


def test_best_legal_lineup_respects_frozen_starters():
    """A locked Thursday TE stays even if a higher-projected TE sits on the bench."""
    players, roster, projections = _lineup_fixture()
    result = best_legal_lineup(
        roster, players, projections, SIMPLE_SCORING,
        frozen_starters={"TE": "p_te2"},
    )
    assert result["starters"]["TE"] == "p_te2"
    assert result["starters"]["QB"] == "p_qb1"


def test_best_legal_lineup_output_passes_validate_lineup():
    players, roster, projections = _lineup_fixture()

    result = best_legal_lineup(roster, players, projections, SIMPLE_SCORING)

    ok, errors = validate_lineup(result, players)
    assert ok is True
    assert errors == []


def test_best_legal_lineup_tie_broken_by_lower_player_id():
    players = {
        "q_zzz": {"name": "Z QB", "pos": "QB"},
        "q_aaa": {"name": "A QB", "pos": "QB"},
    }
    # Deliberately listed with the *higher* id first in bench order, so a
    # pass would only be correct if the tie-break -- not list/dict order
    # -- is what decides the winner.
    roster = {
        "team": "tie-team",
        "faab_remaining": 0,
        "starters": {},
        "bench": ["q_zzz", "q_aaa"],
        "ir": [],
    }
    projections = {
        "q_zzz": {"proj_pts": 10},
        "q_aaa": {"proj_pts": 10},  # exactly tied with q_zzz
    }

    result = best_legal_lineup(roster, players, projections, SIMPLE_SCORING)

    assert result["starters"]["QB"] == "q_aaa"  # lower player_id wins the tie


def test_best_legal_lineup_missing_position_leaves_slot_none_without_raising():
    players = make_players()
    roster = make_roster(starters={"K": None})  # p_k1 excluded from the pool entirely -> no K in the pool
    projections = {
        "p_qb1": {"proj_pts": 20},
        "p_rb1": {"proj_pts": 15},
        "p_rb2": {"proj_pts": 12},
        "p_rb3": {"proj_pts": 6},
        "p_wr1": {"proj_pts": 14},
        "p_wr2": {"proj_pts": 11},
        "p_te1": {"proj_pts": 9},
        "p_def1": {"proj_pts": 7},
    }

    result = best_legal_lineup(roster, players, projections, SIMPLE_SCORING)

    assert result["starters"]["K"] is None
    # the rest of the lineup still fills normally
    assert result["starters"]["QB"] == "p_qb1"
    assert result["starters"]["RB1"] == "p_rb1"
    assert result["starters"]["RB2"] == "p_rb2"
    assert result["starters"]["WR1"] == "p_wr1"
    assert result["starters"]["TE"] == "p_te1"
    assert result["starters"]["DEF"] == "p_def1"
    assert result["starters"]["FLEX"] == "p_rb3"


# --- roster_config_from_league: adapts config/roster.json's flat shape -------

STANDARD_ROSTER_POSITIONS = [
    "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF",
    "BN", "BN", "BN", "BN", "BN", "BN", "IR",
]


def test_roster_config_from_league_standard_shape():
    league_cfg = {
        "roster_positions": STANDARD_ROSTER_POSITIONS,
        "settings": {"num_teams": 12},
    }

    config = roster_config_from_league(league_cfg)

    assert config["starters"] == {
        "QB": ["QB"],
        "RB1": ["RB"],
        "RB2": ["RB"],
        "WR1": ["WR"],
        "WR2": ["WR"],
        "TE": ["TE"],
        "FLEX": ["RB", "WR", "TE"],
        "K": ["K"],
        "DEF": ["DEF"],
    }
    assert config["bench_slots"] == 6
    assert config["ir_slots"] == 1


def test_roster_config_from_league_nondefault_shape_extra_te_and_superflex():
    # A non-default league: two TE slots, a SUPER_FLEX instead of FLEX, and
    # 5 bench spots instead of 6 -- the adapter must carry all of that
    # through rather than silently falling back to standard.
    league_cfg = {
        "roster_positions": [
            "QB", "RB", "RB", "WR", "WR", "TE", "TE", "SUPER_FLEX", "K", "DEF",
            "BN", "BN", "BN", "BN", "BN", "IR",
        ],
        "settings": {"num_teams": 10},
    }

    config = roster_config_from_league(league_cfg)

    assert config["starters"]["TE1"] == ["TE"]
    assert config["starters"]["TE2"] == ["TE"]
    assert "TE" not in config["starters"]  # numbered once TE repeats, no bare "TE" left
    assert config["starters"]["SUPER_FLEX"] == ["QB", "RB", "WR", "TE"]
    assert config["bench_slots"] == 5
    assert config["ir_slots"] == 1


def test_roster_config_from_league_unknown_flex_token_defaults_to_rb_wr_te():
    league_cfg = {
        "roster_positions": ["QB", "RB", "WR", "TE", "MEGA_FLEX", "BN"],
        "settings": {},
    }

    config = roster_config_from_league(league_cfg)

    assert config["starters"]["MEGA_FLEX"] == ["RB", "WR", "TE"]
    assert config["bench_slots"] == 1
    assert config["ir_slots"] == 0


def test_roster_built_to_superflex_adapted_config_passes_validation():
    players = make_players(
        p_qb2={"name": "QB Two", "pos": "QB", "team": "BBB", "status": "Active", "injury": None}
    )
    league_cfg = {
        "roster_positions": [
            "QB", "RB", "RB", "WR", "WR", "TE", "TE", "SUPER_FLEX", "K", "DEF",
            "BN", "BN", "BN", "BN", "BN", "IR",
        ],
        "settings": {"num_teams": 10},
    }
    roster_config = roster_config_from_league(league_cfg)

    # SUPER_FLEX accepts a second QB -- rejected by a plain FLEX slot.
    assert slot_position_ok("SUPER_FLEX", "QB", roster_config) is True
    assert slot_position_ok("FLEX", "QB", roster_config) is False  # no FLEX in this league at all

    roster = make_roster(starters={
        "QB": "p_qb1", "RB1": "p_rb1", "RB2": "p_rb2",
        "WR1": "p_wr1", "WR2": "p_wr2",
        "TE1": "p_te1", "TE2": "p_te2",
        "SUPER_FLEX": "p_qb2",
        "K": "p_k1", "DEF": "p_def1",
    })
    # make_roster()'s defaults use bare "TE"/"FLEX" keys, which aren't part
    # of this custom config's slots (TE1/TE2/SUPER_FLEX instead) -- drop them
    # so `starters` matches exactly what roster_config expects.
    del roster["starters"]["FLEX"]
    del roster["starters"]["TE"]

    ok, errors = validate_roster(roster, players, roster_config)
    assert ok is True
    assert errors == []


# --- a player who is not dressing cannot hold a starting slot ---------------
#
# validate_lineup checked position eligibility and nothing else, so a GM could
# start a player ruled Out and the lineup was "legal" — the fallback never fired
# and the slot scored zero. Questionable is deliberately still legal: Tony
# Soprano starting a questionable Kyler Murray to send Bo Nix a message is bad
# management and entirely his business.

def _lineup_players(qb_injury=None, qb_status="Active"):
    return {
        "qb1": {"name": "QB One", "pos": "QB", "team": "AAA",
                "status": qb_status, "injury": qb_injury},
        "rb1": {"name": "RB One", "pos": "RB", "team": "AAA",
                "status": "Active", "injury": None},
        "rb2": {"name": "RB Two", "pos": "RB", "team": "AAA",
                "status": "Active", "injury": None},
        "wr1": {"name": "WR One", "pos": "WR", "team": "AAA",
                "status": "Active", "injury": None},
        "wr2": {"name": "WR Two", "pos": "WR", "team": "AAA",
                "status": "Active", "injury": None},
        "te1": {"name": "TE One", "pos": "TE", "team": "AAA",
                "status": "Active", "injury": None},
        "k1": {"name": "K One", "pos": "K", "team": "AAA",
               "status": "Active", "injury": None},
        "d1": {"name": "D One", "pos": "DEF", "team": "AAA",
               "status": "Active", "injury": None},
        "fx1": {"name": "FLEX One", "pos": "RB", "team": "AAA",
                "status": "Active", "injury": None},
    }


def _lineup_roster():
    return {"starters": {"QB": "qb1", "RB1": "rb1", "RB2": "rb2", "WR1": "wr1",
                         "WR2": "wr2", "TE": "te1", "FLEX": "fx1", "K": "k1",
                         "DEF": "d1"},
            "bench": [], "ir": []}


def test_a_healthy_lineup_is_legal():
    ok, errors = validate_lineup(_lineup_roster(), _lineup_players())
    assert ok, errors


def test_questionable_is_still_the_gms_call():
    ok, errors = validate_lineup(
        _lineup_roster(), _lineup_players(qb_injury="Questionable"))
    assert ok, errors


@pytest.mark.parametrize("tag", ["Out", "Doubtful", "IR", "Suspended",
                                 "out", "DOUBTFUL"])
def test_a_player_who_is_not_dressing_cannot_start(tag):
    ok, errors = validate_lineup(
        _lineup_roster(), _lineup_players(qb_injury=tag))
    assert not ok
    assert any("cannot start" in e and "QB" in e for e in errors)


def test_the_bar_reads_status_as_well_as_injury():
    """Sleeper sometimes carries it on status rather than injury."""
    ok, errors = validate_lineup(
        _lineup_roster(), _lineup_players(qb_status="Out"))
    assert not ok
    assert any("cannot start" in e for e in errors)


def test_injury_bars_starting_is_tolerant_of_junk():
    assert injury_bars_starting({}) is False
    assert injury_bars_starting({"injury": None}) is False
    assert injury_bars_starting(None) is False

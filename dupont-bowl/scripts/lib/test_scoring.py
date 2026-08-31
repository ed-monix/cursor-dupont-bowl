"""Tests for scripts/lib/scoring.py.

Every expected value below is computed by hand in a comment next to the
fixture, using the live values from config/scoring.default.json, so a
reviewer can check the arithmetic without running anything.
"""

import json
from pathlib import Path

import pytest

from lib.scoring import score_lineup, score_player

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "scoring.default.json"


@pytest.fixture(scope="module")
def scoring() -> dict:
    with open(CONFIG_PATH) as f:
        raw = json.load(f)
    # Drop the non-scoring "_comment" key so it can't accidentally be
    # treated as a stat multiplier.
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def test_scoring_keys_used_match_config(scoring):
    # Sanity check the fixture values below against the actual config, so
    # this test file breaks loudly (not silently) if config/scoring.default.json
    # ever changes.
    assert scoring["pass_yd"] == 0.04
    assert scoring["pass_td"] == 4.0
    assert scoring["pass_int"] == -1.0
    assert scoring["rush_yd"] == 0.1
    assert scoring["rush_td"] == 6.0
    assert scoring["rec"] == 0.5
    assert scoring["rec_yd"] == 0.1
    assert scoring["rec_td"] == 6.0
    assert scoring["fum_lost"] == -2.0


def test_half_ppr_skill_player_hand_computed(scoring):
    # Stat line mixes pass/rush/rec yards+TDs, a reception count, an INT,
    # and a fumble lost, to exercise every "ordinary multiplier" stat.
    stat_line = {
        "pass_yd": 250,
        "pass_td": 2,
        "pass_int": 1,
        "rush_yd": 45,
        "rush_td": 1,
        "rec": 3,
        "rec_yd": 30,
        "rec_td": 0,
        "fum_lost": 1,
    }
    # Hand computation (using config/scoring.default.json values):
    #   pass_yd:  250 * 0.04  = 10.0
    #   pass_td:    2 * 4.0   =  8.0
    #   pass_int:   1 * -1.0  = -1.0
    #   rush_yd:   45 * 0.1   =  4.5
    #   rush_td:    1 * 6.0   =  6.0
    #   rec:        3 * 0.5   =  1.5
    #   rec_yd:    30 * 0.1   =  3.0
    #   rec_td:     0 * 6.0   =  0.0
    #   fum_lost:   1 * -2.0  = -2.0
    #   -----------------------------
    #   sum: 10.0+8.0-1.0+4.5+6.0+1.5+3.0+0.0-2.0 = 30.0
    expected = 30.0
    assert score_player(stat_line, scoring) == pytest.approx(expected, abs=0.01)


def test_unknown_stat_keys_are_ignored(scoring):
    # Same fixture as above, plus stat keys that don't exist in the
    # scoring config at all -- must not change the total.
    stat_line = {
        "pass_yd": 250,
        "pass_td": 2,
        "pass_int": 1,
        "rush_yd": 45,
        "rush_td": 1,
        "rec": 3,
        "rec_yd": 30,
        "rec_td": 0,
        "fum_lost": 1,
        "snap_pct": 87,  # not a scoring key -- must be ignored
        "kick_return_yd": 12,  # not a scoring key -- must be ignored
    }
    expected = 30.0  # same hand computation as above
    assert score_player(stat_line, scoring) == pytest.approx(expected, abs=0.01)


def test_dst_numeric_pts_allow_tier(scoring):
    # 17 points allowed falls in the 14-20 tier -> pts_allow_14_20 = 1.0.
    stat_line = {"pts_allow": 17, "sack": 3, "int": 1}
    # Hand computation:
    #   pts_allow tier bonus (14-20):      1.0
    #   sack:  3 * 1.0 = 3.0
    #   int:   1 * 2.0 = 2.0
    #   -----------------------------
    #   sum: 1.0 + 3.0 + 2.0 = 6.0
    expected = 6.0
    assert score_player(stat_line, scoring) == pytest.approx(expected, abs=0.01)


def test_dst_tier_boundaries(scoring):
    # Boundary values: 0, 6/7, 13/14, 20/21, 27/28, 34/35 must land in the
    # tiers the boundary belongs to per config/scoring.default.json.
    cases = [
        (0, "pts_allow_0", 10.0),
        (6, "pts_allow_1_6", 7.0),
        (7, "pts_allow_7_13", 4.0),
        (13, "pts_allow_7_13", 4.0),
        (14, "pts_allow_14_20", 1.0),
        (20, "pts_allow_14_20", 1.0),
        (21, "pts_allow_21_27", 0.0),
        (27, "pts_allow_21_27", 0.0),
        (28, "pts_allow_28_34", -1.0),
        (34, "pts_allow_28_34", -1.0),
        (35, "pts_allow_35p", -4.0),
        (50, "pts_allow_35p", -4.0),
    ]
    for pts_allowed, tier_key, expected in cases:
        assert scoring[tier_key] == expected, tier_key  # confirms fixture matches config
        got = score_player({"pts_allow": pts_allowed}, scoring)
        assert got == pytest.approx(expected, abs=0.01), (pts_allowed, tier_key)


def test_dst_pre_bucketed_flag_matches_numeric_form(scoring):
    # Pre-bucketed flag form of the same DST game as
    # test_dst_numeric_pts_allow_tier: {"pts_allow_14_20": 1} instead of
    # {"pts_allow": 17}. As an ordinary multiplier key:
    #   pts_allow_14_20: 1 * 1.0 = 1.0
    #   sack:  3 * 1.0 = 3.0
    #   int:   1 * 2.0 = 2.0
    #   -----------------------------
    #   sum: 1.0 + 3.0 + 2.0 = 6.0
    numeric_form = {"pts_allow": 17, "sack": 3, "int": 1}
    flagged_form = {"pts_allow_14_20": 1, "sack": 3, "int": 1}

    numeric_score = score_player(numeric_form, scoring)
    flagged_score = score_player(flagged_form, scoring)

    assert flagged_score == pytest.approx(6.0, abs=0.01)
    assert flagged_score == pytest.approx(numeric_score, abs=0.01)


def test_dst_both_forms_present_never_double_counts(scoring):
    # Pathological input: both the numeric and pre-bucketed forms present
    # for the same game. The numeric form must win and the tier bonus must
    # be counted exactly once (i.e. must equal the numeric-only score, not
    # numeric + pre-bucketed).
    stat_line = {"pts_allow": 17, "pts_allow_14_20": 1, "sack": 3, "int": 1}
    got = score_player(stat_line, scoring)
    assert got == pytest.approx(6.0, abs=0.01)  # not 7.0 (which would be double-counted)


def test_kicker_fg_buckets_and_xp(scoring):
    stat_line = {
        "fgm_0_19": 1,
        "fgm_20_29": 0,
        "fgm_30_39": 1,
        "fgm_40_49": 1,
        "fgm_50p": 0,
        "fgmiss": 1,
        "xpm": 3,
        "xpmiss": 1,
    }
    # Hand computation:
    #   fgm_0_19:   1 * 3.0  =  3.0
    #   fgm_20_29:  0 * 3.0  =  0.0
    #   fgm_30_39:  1 * 3.0  =  3.0
    #   fgm_40_49:  1 * 4.0  =  4.0
    #   fgm_50p:    0 * 5.0  =  0.0
    #   fgmiss:     1 * -1.0 = -1.0
    #   xpm:        3 * 1.0  =  3.0
    #   xpmiss:     1 * -1.0 = -1.0
    #   -----------------------------
    #   sum: 3.0+0.0+3.0+4.0+0.0-1.0+3.0-1.0 = 11.0
    expected = 11.0
    assert score_player(stat_line, scoring) == pytest.approx(expected, abs=0.01)


def test_score_lineup_starters_only_with_null_slot(scoring):
    roster = {
        "team": "test-team",
        "faab_remaining": 100,
        "starters": {"QB": "P1", "RB1": "P2", "FLEX": None},
        "bench": ["P99"],
        "ir": [],
    }
    stats = {
        "P1": {"pass_yd": 200, "pass_td": 2},
        "P2": {"rush_yd": 50, "rush_td": 1},
        # P99 is on the bench with a huge stat line -- must NOT be scored.
        "P99": {"rush_yd": 1000, "rush_td": 10},
    }
    # Hand computation:
    #   P1: pass_yd 200 * 0.04 = 8.0 ; pass_td 2 * 4.0 = 8.0  -> 16.0
    #   P2: rush_yd  50 * 0.1  = 5.0 ; rush_td 1 * 6.0 = 6.0  -> 11.0
    #   FLEX slot is None -> contributes 0, omitted from the result dict
    #   P99 is bench -> ignored entirely
    #   total = 16.0 + 11.0 = 27.0
    result = score_lineup(roster, stats, scoring)

    assert result["P1"] == pytest.approx(16.0, abs=0.01)
    assert result["P2"] == pytest.approx(11.0, abs=0.01)
    assert "P99" not in result  # bench player must not appear
    assert result["total"] == pytest.approx(27.0, abs=0.01)
    # Null FLEX slot has no player_id, so it's simply absent (not a "None" key).
    assert None not in result

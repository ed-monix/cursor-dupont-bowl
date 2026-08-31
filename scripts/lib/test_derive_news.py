"""Tests for derive_news.py."""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import derive_news as dn


# ======================
# Overperformer / Underperformer Tests
# ======================

def test_overperformer_basic():
    """A player scoring above projection is detected as an overperformer."""
    stats = {"p1": {"rec": 8, "rec_yd": 120}}
    projections = {"p1": {"rec": 6, "rec_yd": 100}}
    players = {"p1": {"name": "Alice", "pos": "WR", "team": "SF"}}
    scoring = {"rec": 0.5, "rec_yd": 0.1}
    # actual = 8*0.5 + 120*0.1 = 4 + 12 = 16
    # projected = 6*0.5 + 100*0.1 = 3 + 10 = 13
    # delta = 3

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    assert len(overperf) == 1
    h = overperf[0]
    assert h["player_id"] == "p1"
    assert h["player_name"] == "Alice"
    assert h["actual"] == 16.0
    assert h["projected"] == 13.0
    assert h["delta"] == 3.0


def test_underperformer_basic():
    """A player scoring below projection is detected as an underperformer."""
    stats = {"p1": {"pass_yd": 150, "pass_td": 0}}
    projections = {"p1": {"pass_yd": 250, "pass_td": 1}}
    players = {"p1": {"name": "Bob", "pos": "QB", "team": "KC"}}
    scoring = {"pass_yd": 0.04, "pass_td": 4.0}
    # actual = 150*0.04 + 0*4 = 6 + 0 = 6
    # projected = 250*0.04 + 1*4 = 10 + 4 = 14
    # delta = -8

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    underperf = [h for h in headlines if h["kind"] == "underperformer"]
    assert len(underperf) == 1
    h = underperf[0]
    assert h["player_id"] == "p1"
    assert h["player_name"] == "Bob"
    assert h["actual"] == 6.0
    assert h["projected"] == 14.0
    assert h["delta"] == -8.0


def test_overperformer_top_n():
    """Only top N overperformers are included (sorted by magnitude descending)."""
    stats = {
        "p1": {"rec": 10},
        "p2": {"rec": 8},
        "p3": {"rec": 6},
        "p4": {"rec": 4},
    }
    projections = {
        "p1": {"rec": 5},  # delta = 2.5
        "p2": {"rec": 5},  # delta = 1.5
        "p3": {"rec": 5},  # delta = 0.5
        "p4": {"rec": 5},  # delta = -0.5
    }
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "WR", "team": "SF"},
        "p3": {"name": "C", "pos": "WR", "team": "SF"},
        "p4": {"name": "D", "pos": "WR", "team": "SF"},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring, top_n=2)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    # Should have exactly 2 (top_n=2)
    assert len(overperf) == 2
    # First should be p1 (highest delta)
    assert overperf[0]["player_id"] == "p1"
    assert overperf[0]["delta"] == 2.5
    # Second should be p2
    assert overperf[1]["player_id"] == "p2"
    assert overperf[1]["delta"] == 1.5


def test_underperformer_top_n():
    """Only top N underperformers are included (sorted by magnitude descending)."""
    stats = {
        "p1": {"rec": 1},
        "p2": {"rec": 2},
        "p3": {"rec": 3},
    }
    projections = {
        "p1": {"rec": 10},  # delta = -4.5
        "p2": {"rec": 10},  # delta = -4.0
        "p3": {"rec": 10},  # delta = -3.5
    }
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "WR", "team": "SF"},
        "p3": {"name": "C", "pos": "WR", "team": "SF"},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring, top_n=2)

    underperf = [h for h in headlines if h["kind"] == "underperformer"]
    assert len(underperf) == 2
    # First should be p1 (most negative delta, magnitude 4.5)
    assert underperf[0]["player_id"] == "p1"
    assert underperf[0]["delta"] == -4.5
    # Second should be p2
    assert underperf[1]["player_id"] == "p2"
    assert underperf[1]["delta"] == -4.0


def test_overperformer_ignores_non_matching_projections():
    """Stats without matching projections are ignored."""
    stats = {
        "p1": {"rec": 10},
        "p2": {"rec": 8},
    }
    projections = {
        "p1": {"rec": 5},  # p1 has projection
        # p2 has no projection — should be ignored
    }
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "WR", "team": "SF"},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    # Only p1 should be included
    assert len(overperf) == 1
    assert overperf[0]["player_id"] == "p1"


def test_no_overperformers_when_all_underperform():
    """When all players underperform, overperformer list is empty."""
    stats = {"p1": {"rec": 2}, "p2": {"rec": 3}}
    projections = {"p1": {"rec": 10}, "p2": {"rec": 10}}
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "WR", "team": "SF"},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    assert len(overperf) == 0


def test_player_name_missing_uses_id():
    """If player_id is not in players dict, use the id as name."""
    stats = {"p_unknown": {"rec": 10}}
    projections = {"p_unknown": {"rec": 5}}
    players = {}  # Empty — p_unknown not defined
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    assert len(overperf) == 1
    assert overperf[0]["player_name"] == "p_unknown"


# ======================
# Blowout Tests
# ======================

def test_blowout_largest_margin():
    """The largest margin is picked as the top blowout."""
    matchups = {
        "matchups": [
            {"home": "team_a", "away": "team_b", "home_score": 120.0, "away_score": 80.0},  # margin 40
            {"home": "team_c", "away": "team_d", "home_score": 100.0, "away_score": 95.0},  # margin 5
        ]
    }
    players = {}
    scoring = {}

    headlines = dn.derive_news({}, {}, matchups, [], players, scoring)

    blowouts = [h for h in headlines if h["kind"] == "blowout"]
    assert len(blowouts) == 2  # Both have margins > 0
    # First should be the largest margin
    assert blowouts[0]["margin"] == 40
    assert blowouts[0]["home_team"] == "team_a"
    assert blowouts[0]["away_team"] == "team_b"
    assert blowouts[0]["home_score"] == 120.0
    assert blowouts[0]["away_score"] == 80.0


def test_blowout_no_matchups():
    """No matchups dict yields no blowouts."""
    headlines = dn.derive_news({}, {}, None, [], {}, {})

    blowouts = [h for h in headlines if h["kind"] == "blowout"]
    assert len(blowouts) == 0


def test_blowout_empty_matchups_list():
    """Empty matchups list yields no blowouts."""
    matchups = {"matchups": []}
    headlines = dn.derive_news({}, {}, matchups, [], {}, {})

    blowouts = [h for h in headlines if h["kind"] == "blowout"]
    assert len(blowouts) == 0


def test_blowout_zero_margin_ignored():
    """Tied matchups (margin=0) are not included."""
    matchups = {
        "matchups": [
            {"home": "team_a", "away": "team_b", "home_score": 100.0, "away_score": 100.0},  # margin 0
        ]
    }
    headlines = dn.derive_news({}, {}, matchups, [], {}, {})

    blowouts = [h for h in headlines if h["kind"] == "blowout"]
    assert len(blowouts) == 0


def test_blowout_away_win():
    """Blowouts work when away team wins (margin calculation is abs())."""
    matchups = {
        "matchups": [
            {"home": "team_a", "away": "team_b", "home_score": 50.0, "away_score": 120.0},  # margin 70
        ]
    }
    headlines = dn.derive_news({}, {}, matchups, [], {}, {})

    blowouts = [h for h in headlines if h["kind"] == "blowout"]
    assert len(blowouts) == 1
    assert blowouts[0]["margin"] == 70
    assert blowouts[0]["home_score"] == 50.0
    assert blowouts[0]["away_score"] == 120.0


# ======================
# Big Bid Tests
# ======================

def test_big_bid_basic():
    """Top waiver claim bids are detected."""
    transactions = [
        {
            "team": "team_a",
            "action": "waiver_claim",
            "bid": 25,
            "players": ["p1"],
        },
    ]
    players = {"p1": {"name": "Alice", "pos": "WR", "team": "SF"}}
    scoring = {}

    headlines = dn.derive_news({}, {}, None, transactions, players, scoring)

    bids = [h for h in headlines if h["kind"] == "big_bid"]
    assert len(bids) == 1
    assert bids[0]["team"] == "team_a"
    assert bids[0]["player_id"] == "p1"
    assert bids[0]["player_name"] == "Alice"
    assert bids[0]["bid"] == 25


def test_big_bid_top_n():
    """Only top N bids are included (sorted by bid descending)."""
    transactions = [
        {"team": "team_a", "action": "waiver_claim", "bid": 10, "players": ["p1"]},
        {"team": "team_b", "action": "waiver_claim", "bid": 25, "players": ["p2"]},
        {"team": "team_c", "action": "waiver_claim", "bid": 15, "players": ["p3"]},
        {"team": "team_d", "action": "waiver_claim", "bid": 5, "players": ["p4"]},
    ]
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "RB", "team": "TB"},
        "p3": {"name": "C", "pos": "WR", "team": "SF"},
        "p4": {"name": "D", "pos": "WR", "team": "SF"},
    }
    scoring = {}

    headlines = dn.derive_news({}, {}, None, transactions, players, scoring, top_n=2)

    bids = [h for h in headlines if h["kind"] == "big_bid"]
    assert len(bids) == 2
    # First should be team_b with bid 25
    assert bids[0]["team"] == "team_b"
    assert bids[0]["bid"] == 25
    # Second should be team_c with bid 15
    assert bids[1]["team"] == "team_c"
    assert bids[1]["bid"] == 15


def test_big_bid_ignores_non_waiver_claims():
    """Non-waiver_claim transactions are ignored."""
    transactions = [
        {"team": "team_a", "action": "add", "bid": None, "players": ["p1"]},
        {"team": "team_b", "action": "waiver_claim", "bid": 20, "players": ["p2"]},
        {"team": "team_c", "action": "trade", "bid": None, "players": ["p3", "p4"]},
    ]
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF"},
        "p2": {"name": "B", "pos": "RB", "team": "TB"},
        "p3": {"name": "C", "pos": "WR", "team": "SF"},
        "p4": {"name": "D", "pos": "WR", "team": "SF"},
    }
    scoring = {}

    headlines = dn.derive_news({}, {}, None, transactions, players, scoring)

    bids = [h for h in headlines if h["kind"] == "big_bid"]
    # Only the waiver_claim should be included
    assert len(bids) == 1
    assert bids[0]["team"] == "team_b"


def test_big_bid_player_name_missing_uses_id():
    """If a player is not in players dict, use the id as name."""
    transactions = [
        {"team": "team_a", "action": "waiver_claim", "bid": 20, "players": ["p_unknown"]},
    ]
    players = {}
    scoring = {}

    headlines = dn.derive_news({}, {}, None, transactions, players, scoring)

    bids = [h for h in headlines if h["kind"] == "big_bid"]
    assert len(bids) == 1
    assert bids[0]["player_name"] == "p_unknown"


def test_big_bid_players_array_first_element():
    """The first element of players array is the added player."""
    transactions = [
        {"team": "team_a", "action": "waiver_claim", "bid": 20, "players": ["p_add", "p_drop"]},
    ]
    players = {
        "p_add": {"name": "Added", "pos": "WR", "team": "SF"},
        "p_drop": {"name": "Dropped", "pos": "RB", "team": "TB"},
    }
    scoring = {}

    headlines = dn.derive_news({}, {}, None, transactions, players, scoring)

    bids = [h for h in headlines if h["kind"] == "big_bid"]
    assert len(bids) == 1
    # Should reference the added player (first in array)
    assert bids[0]["player_id"] == "p_add"
    assert bids[0]["player_name"] == "Added"


# ======================
# Injury Change Tests
# ======================

def test_injury_change_status_change():
    """A player's status change is detected when prior_players is provided."""
    players = {"p1": {"name": "Alice", "pos": "WR", "team": "SF", "status": "Active", "injury": None}}
    prior_players = {"p1": {"name": "Alice", "pos": "WR", "team": "SF", "status": "Out", "injury": "Hamstring"}}

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=prior_players)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 1
    assert injuries[0]["player_id"] == "p1"
    assert injuries[0]["player_name"] == "Alice"
    assert injuries[0]["old_status"] == "Out"
    assert injuries[0]["new_status"] == "Active"


def test_injury_change_injury_change():
    """A player's injury status change is detected."""
    players = {"p1": {"name": "Bob", "pos": "RB", "team": "TB", "status": "Out", "injury": None}}
    prior_players = {"p1": {"name": "Bob", "pos": "RB", "team": "TB", "status": "Out", "injury": "Ankle"}}

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=prior_players)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 1
    assert injuries[0]["old_injury"] == "Ankle"
    assert injuries[0]["new_injury"] is None


def test_injury_change_both_change():
    """When both status and injury change, both are noted."""
    players = {"p1": {"name": "Charlie", "pos": "WR", "team": "SF", "status": "Active", "injury": None}}
    prior_players = {"p1": {"name": "Charlie", "pos": "WR", "team": "SF", "status": "Out", "injury": "Hamstring"}}

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=prior_players)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 1
    h = injuries[0]
    assert h["player_id"] == "p1"
    # Text should mention both changes
    assert "status" in h["text"].lower() and "injury" in h["text"].lower()


def test_injury_change_none_when_no_change():
    """When status/injury don't change, no injury headline is generated."""
    players = {"p1": {"name": "Diana", "pos": "TE", "team": "KC", "status": "Active", "injury": None}}
    prior_players = {"p1": {"name": "Diana", "pos": "TE", "team": "KC", "status": "Active", "injury": None}}

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=prior_players)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 0


def test_injury_change_skipped_when_prior_players_none():
    """When prior_players is None, injury_change headlines are not generated even if players change."""
    players = {"p1": {"name": "Eve", "pos": "QB", "team": "KC", "status": "Active", "injury": None}}

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=None)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 0


def test_injury_change_ignores_new_players():
    """Players that appear in current but not in prior are ignored."""
    players = {"p1": {"name": "Frank", "pos": "WR", "team": "SF", "status": "Active", "injury": None}}
    prior_players = {}  # p1 not in prior

    headlines = dn.derive_news({}, {}, None, [], players, {}, prior_players=prior_players)

    injuries = [h for h in headlines if h["kind"] == "injury_change"]
    assert len(injuries) == 0


# ======================
# Ordering and Grouping Tests
# ======================

def test_headlines_grouped_by_kind():
    """Headlines are returned in kind order: overperformer, underperformer, blowout, big_bid, injury_change."""
    stats = {"p1": {"rec": 10}}
    projections = {"p1": {"rec": 5}}
    matchups = {"matchups": [{"home": "ta", "away": "tb", "home_score": 100.0, "away_score": 50.0}]}
    transactions = [{"team": "tc", "action": "waiver_claim", "bid": 20, "players": ["p2"]}]
    players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF", "status": "Active", "injury": None},
        "p2": {"name": "B", "pos": "RB", "team": "TB", "status": "Active", "injury": None},
    }
    prior_players = {
        "p1": {"name": "A", "pos": "WR", "team": "SF", "status": "Out", "injury": "Ankle"},
        "p2": {"name": "B", "pos": "RB", "team": "TB", "status": "Active", "injury": None},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, matchups, transactions, players, scoring, prior_players)

    kinds = [h["kind"] for h in headlines]
    # Extract indices of each kind
    overperf_idx = kinds.index("overperformer") if "overperformer" in kinds else -1
    underperf_idx = kinds.index("underperformer") if "underperformer" in kinds else -1
    blowout_idx = kinds.index("blowout") if "blowout" in kinds else -1
    big_bid_idx = kinds.index("big_bid") if "big_bid" in kinds else -1
    injury_idx = kinds.index("injury_change") if "injury_change" in kinds else -1

    # Check ordering: overperformer < underperformer < blowout < big_bid < injury_change
    if overperf_idx >= 0 and underperf_idx >= 0:
        assert overperf_idx < underperf_idx
    if underperf_idx >= 0 and blowout_idx >= 0:
        assert underperf_idx < blowout_idx
    if blowout_idx >= 0 and big_bid_idx >= 0:
        assert blowout_idx < big_bid_idx
    if big_bid_idx >= 0 and injury_idx >= 0:
        assert big_bid_idx < injury_idx


def test_deterministic_tiebreak_on_player_id():
    """Within overperformers, ties are broken by player_id."""
    stats = {
        "p_z": {"rec": 10},
        "p_a": {"rec": 10},
    }
    projections = {
        "p_z": {"rec": 5},  # delta = 2.5
        "p_a": {"rec": 5},  # delta = 2.5 (tie)
    }
    players = {
        "p_z": {"name": "Z", "pos": "WR", "team": "SF"},
        "p_a": {"name": "A", "pos": "WR", "team": "SF"},
    }
    scoring = {"rec": 0.5}

    headlines = dn.derive_news(stats, projections, None, [], players, scoring)

    overperf = [h for h in headlines if h["kind"] == "overperformer"]
    # Both should appear; tie-break by player_id
    assert len(overperf) == 2
    # p_a comes before p_z alphabetically (tiebreaker)
    assert overperf[0]["player_id"] == "p_a"
    assert overperf[1]["player_id"] == "p_z"

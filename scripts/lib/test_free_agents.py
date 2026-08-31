"""Tests for scripts/free_agents.py. Pure, no network, no external files."""

import free_agents


SCORING = {"pass_yd": 0.04, "pass_td": 4.0, "rush_yd": 0.1, "rush_td": 6.0,
           "rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0}


def make_players():
    return {
        "p_qb": {"name": "Rostered QB", "pos": "QB", "team": "AAA"},
        "p_rb": {"name": "Rostered RB", "pos": "RB", "team": "AAA"},
        "p_bench": {"name": "Benched WR", "pos": "WR", "team": "BBB"},
        "p_ir": {"name": "Injured TE", "pos": "TE", "team": "CCC"},
        "fa_wr": {"name": "Free Agent WR", "pos": "WR", "team": "DDD"},
        "fa_rb": {"name": "Free Agent RB", "pos": "RB", "team": "EEE"},
        "fa_noproj": {"name": "Deep Sleeper", "pos": "WR", "team": "FFF"},
    }


def make_rosters():
    # One team holds p_qb (starter), p_bench (bench), p_ir (ir); another holds p_rb.
    return {
        "team-a": {"team": "team-a", "faab_remaining": 50,
                   "starters": {"QB": "p_qb", "RB1": None, "WR1": None},
                   "bench": ["p_bench"], "ir": ["p_ir"]},
        "team-b": {"team": "team-b", "faab_remaining": 80,
                   "starters": {"QB": None, "RB1": "p_rb"}, "bench": [], "ir": []},
    }


def test_rostered_players_excluded_free_agents_included():
    players = make_players()
    projections = {
        "fa_wr": {"rec": 6, "rec_yd": 80, "rec_td": 1},   # 0.5*6 + 0.1*80 + 6 = 3 + 8 + 6 = 17.0
        "fa_rb": {"rush_yd": 55, "rush_td": 1},            # 0.1*55 + 6 = 5.5 + 6 = 11.5
        # fa_noproj intentionally absent -> proj_pts 0.0
    }
    fa = free_agents.derive_free_agents(players, make_rosters(), projections, SCORING)

    # Rostered players (starter, bench, ir, other-team starter) are all excluded.
    for pid in ("p_qb", "p_rb", "p_bench", "p_ir"):
        assert pid not in fa
    # Free agents are included.
    assert set(fa) == {"fa_wr", "fa_rb", "fa_noproj"}


def test_projected_points_attached_and_hand_computed():
    players = make_players()
    projections = {
        "fa_wr": {"rec": 6, "rec_yd": 80, "rec_td": 1},   # 17.0 (see above)
        "fa_rb": {"rush_yd": 55, "rush_td": 1},            # 11.5
    }
    fa = free_agents.derive_free_agents(players, make_rosters(), projections, SCORING)

    assert fa["fa_wr"]["proj_pts"] == 17.0
    assert fa["fa_rb"]["proj_pts"] == 11.5
    # A free agent with no projection row scores 0.0, not an error.
    assert fa["fa_noproj"]["proj_pts"] == 0.0
    # Metadata carried through.
    assert fa["fa_wr"]["name"] == "Free Agent WR"
    assert fa["fa_wr"]["pos"] == "WR"
    assert fa["fa_wr"]["team"] == "DDD"


def test_accepts_list_of_rosters_not_just_dict():
    players = make_players()
    rosters_list = list(make_rosters().values())
    fa = free_agents.derive_free_agents(players, rosters_list, {}, SCORING)
    assert "p_qb" not in fa and "fa_wr" in fa


def test_rostered_player_ids_spans_starters_bench_ir():
    ids = free_agents.rostered_player_ids(make_rosters())
    assert ids == {"p_qb", "p_rb", "p_bench", "p_ir"}


def test_status_and_injury_carried_from_players():
    """Verify that status and injury fields from players.json are included in output."""
    players = {
        "fa_healthy": {"name": "Healthy WR", "pos": "WR", "team": "AAA", "status": "active", "injury": None},
        "fa_injured": {"name": "Injured RB", "pos": "RB", "team": "BBB", "status": "out", "injury": "hamstring"},
    }
    rosters = {}
    projections = {}
    fa = free_agents.derive_free_agents(players, rosters, projections, SCORING)

    assert fa["fa_healthy"]["status"] == "active"
    assert fa["fa_healthy"]["injury"] is None
    assert fa["fa_injured"]["status"] == "out"
    assert fa["fa_injured"]["injury"] == "hamstring"


def test_proj_contains_whitelisted_keys_by_position():
    """Verify that proj dict contains only whitelisted keys present in the projection row."""
    players = {
        "qb": {"name": "QB", "pos": "QB", "team": "AAA"},
        "rb": {"name": "RB", "pos": "RB", "team": "BBB"},
        "wr": {"name": "WR", "pos": "WR", "team": "CCC"},
        "te": {"name": "TE", "pos": "TE", "team": "DDD"},
        "k": {"name": "K", "pos": "K", "team": "EEE"},
        "def": {"name": "DEF", "pos": "DEF", "team": "FFF"},
    }
    projections = {
        # QB: has pass_yd, pass_td (whitelisted), pass_int (whitelisted), but no rush_yd
        "qb": {"pass_yd": 250, "pass_td": 2, "pass_int": 1, "pass_cmp": 20},
        # RB: has rush_yd, rec (whitelisted), but not rush_td or rec_yd
        "rb": {"rush_yd": 60, "rec": 3, "rush_cmp": 1},
        # WR: has rec, rec_yd, rec_td (all whitelisted)
        "wr": {"rec": 8, "rec_yd": 120, "rec_td": 1},
        # TE: has rec, rec_yd (whitelisted), no rec_td
        "te": {"rec": 4, "rec_yd": 50},
        # K: has fgm, fga, xpm (all whitelisted)
        "k": {"fgm": 2, "fga": 3, "xpm": 1},
        # DEF: has pts_allow, sack (whitelisted), no int
        "def": {"pts_allow": 18, "sack": 7},
    }
    rosters = {}
    fa = free_agents.derive_free_agents(players, rosters, projections, SCORING)

    # QB proj: pass_yd, pass_td, pass_int present; pass_cmp and rush_yd excluded
    assert set(fa["qb"]["proj"].keys()) == {"pass_yd", "pass_td", "pass_int"}
    assert fa["qb"]["proj"]["pass_yd"] == 250
    assert fa["qb"]["proj"]["pass_td"] == 2
    assert fa["qb"]["proj"]["pass_int"] == 1

    # RB proj: rush_yd, rec present; rush_td and rec_yd not in row; rush_cmp excluded
    assert set(fa["rb"]["proj"].keys()) == {"rush_yd", "rec"}
    assert fa["rb"]["proj"]["rush_yd"] == 60
    assert fa["rb"]["proj"]["rec"] == 3

    # WR proj: all three whitelisted keys present
    assert set(fa["wr"]["proj"].keys()) == {"rec", "rec_yd", "rec_td"}
    assert fa["wr"]["proj"]["rec"] == 8
    assert fa["wr"]["proj"]["rec_yd"] == 120
    assert fa["wr"]["proj"]["rec_td"] == 1

    # TE proj: rec, rec_yd present; rec_td not in row
    assert set(fa["te"]["proj"].keys()) == {"rec", "rec_yd"}
    assert fa["te"]["proj"]["rec"] == 4
    assert fa["te"]["proj"]["rec_yd"] == 50

    # K proj: all three whitelisted keys present
    assert set(fa["k"]["proj"].keys()) == {"fgm", "fga", "xpm"}
    assert fa["k"]["proj"]["fgm"] == 2
    assert fa["k"]["proj"]["fga"] == 3
    assert fa["k"]["proj"]["xpm"] == 1

    # DEF proj: pts_allow, sack present; int not in row
    assert set(fa["def"]["proj"].keys()) == {"pts_allow", "sack"}
    assert fa["def"]["proj"]["pts_allow"] == 18
    assert fa["def"]["proj"]["sack"] == 7


def test_last_wk_pts_computed_from_prior_stats():
    """Verify that last_wk_pts is computed from prior_stats when provided."""
    players = {
        "fa": {"name": "Free Agent", "pos": "WR", "team": "AAA"},
    }
    rosters = {}
    projections = {"fa": {"rec": 8, "rec_yd": 100, "rec_td": 1}}
    prior_stats = {
        "fa": {"rec": 6, "rec_yd": 90},  # 0.5*6 + 0.1*90 = 3 + 9 = 12.0
    }

    fa = free_agents.derive_free_agents(players, rosters, projections, SCORING, prior_stats)
    assert fa["fa"]["last_wk_pts"] == 12.0


def test_last_wk_pts_none_when_prior_stats_omitted():
    """Verify that last_wk_pts is None when prior_stats is not provided."""
    players = {
        "fa": {"name": "Free Agent", "pos": "WR", "team": "AAA"},
    }
    rosters = {}
    projections = {"fa": {"rec": 8, "rec_yd": 100, "rec_td": 1}}

    fa = free_agents.derive_free_agents(players, rosters, projections, SCORING)
    assert fa["fa"]["last_wk_pts"] is None


def test_last_wk_pts_none_when_player_not_in_prior_stats():
    """Verify that last_wk_pts is None when the player is not in prior_stats."""
    players = {
        "fa": {"name": "Free Agent", "pos": "WR", "team": "AAA"},
    }
    rosters = {}
    projections = {"fa": {"rec": 8, "rec_yd": 100, "rec_td": 1}}
    prior_stats = {}  # fa is not in prior_stats

    fa = free_agents.derive_free_agents(players, rosters, projections, SCORING, prior_stats)
    assert fa["fa"]["last_wk_pts"] is None

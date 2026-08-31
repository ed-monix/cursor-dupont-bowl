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

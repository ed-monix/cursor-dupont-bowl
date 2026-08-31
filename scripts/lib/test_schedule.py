"""Tests for scripts/lib/schedule_gen.py. Pure, no network, no files."""

import itertools

import pytest

from lib.schedule_gen import PLAYOFF_TEMPLATE, generate

TEAMS = [f"team-{i:02d}" for i in range(1, 13)]  # team-01 .. team-12


# --- AC: every team appears exactly once per week, all 14 weeks -------------

def test_every_week_has_six_pairs_and_twelve_distinct_teams():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]
    assert set(regular.keys()) == {str(w) for w in range(1, 15)}
    for week, pairs in regular.items():
        assert len(pairs) == 6, f"week {week} has {len(pairs)} pairs, expected 6"
        appearances = [team for pair in pairs for team in pair]
        assert len(appearances) == 12, f"week {week}: {len(appearances)} appearances, expected 12"
        assert set(appearances) == set(TEAMS), f"week {week} missing/extra teams"
        assert len(set(appearances)) == 12, f"week {week}: a team appears twice"


def test_no_team_plays_itself_any_week():
    schedule = generate(TEAMS)
    for week, pairs in schedule["regular_season"].items():
        for a, b in pairs:
            assert a != b, f"week {week}: team {a} scheduled against itself"


# --- AC: no repeat opponent across weeks 1-11 (66 unique pairs, one each) --

def test_weeks_1_to_11_cover_every_unique_pair_exactly_once():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]

    seen_pairs = []
    for week in range(1, 12):
        for a, b in regular[str(week)]:
            seen_pairs.append(frozenset((a, b)))

    all_possible_pairs = {frozenset(p) for p in itertools.combinations(TEAMS, 2)}
    assert len(all_possible_pairs) == 66

    # Every pair appears; no pair appears more than once (they're equal in
    # length and content, but check both directions explicitly for a clear
    # failure message either way).
    assert set(seen_pairs) == all_possible_pairs
    assert len(seen_pairs) == 66
    assert len(seen_pairs) == len(set(seen_pairs)), "a pair repeated within weeks 1-11"


def test_weeks_1_to_11_have_no_duplicate_pair_across_weeks():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]
    counts = {}
    for week in range(1, 12):
        for a, b in regular[str(week)]:
            key = frozenset((a, b))
            counts[key] = counts.get(key, 0) + 1
    repeats = {pair: n for pair, n in counts.items() if n > 1}
    assert repeats == {}, f"pairs repeated before week 12: {repeats}"


# --- AC: opponent counts -- 14 weeks means 14 games per team, no self-play --

def test_every_team_plays_exactly_fourteen_games():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]
    game_counts = {team: 0 for team in TEAMS}
    for pairs in regular.values():
        for a, b in pairs:
            game_counts[a] += 1
            game_counts[b] += 1
    assert game_counts == {team: 14 for team in TEAMS}


def test_each_team_faces_every_other_team_at_least_once_by_week_11():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]
    opponents = {team: set() for team in TEAMS}
    for week in range(1, 12):
        for a, b in regular[str(week)]:
            opponents[a].add(b)
            opponents[b].add(a)
    for team in TEAMS:
        assert opponents[team] == set(TEAMS) - {team}, f"{team} missing an opponent by week 11"


# --- weeks 12-14: repeats are allowed (and, per this generator, happen) ----

def test_weeks_12_to_14_reuse_earlier_weeks_pairings():
    schedule = generate(TEAMS)
    regular = schedule["regular_season"]
    for later, earlier in ((12, 1), (13, 2), (14, 3)):
        later_pairs = {frozenset(p) for p in regular[str(later)]}
        earlier_pairs = {frozenset(p) for p in regular[str(earlier)]}
        assert later_pairs == earlier_pairs


# --- AC: playoff template bye structure -------------------------------------

def test_week_15_excludes_seeds_one_and_two():
    schedule = generate(TEAMS)
    week15_teams = {t for pair in schedule["playoffs"]["15"] for t in pair}
    assert "seed_1" not in week15_teams
    assert "seed_2" not in week15_teams
    assert week15_teams == {"seed_3", "seed_4", "seed_5", "seed_6"}


def test_week_15_pairs_three_six_and_four_five():
    schedule = generate(TEAMS)
    pairs = {frozenset(p) for p in schedule["playoffs"]["15"]}
    assert pairs == {frozenset(("seed_3", "seed_6")), frozenset(("seed_4", "seed_5"))}


def test_playoff_weeks_present_with_expected_game_counts():
    schedule = generate(TEAMS)
    playoffs = schedule["playoffs"]
    assert set(playoffs.keys()) == {"15", "16", "17"}
    assert len(playoffs["15"]) == 2  # quarterfinals (byes for 1, 2)
    assert len(playoffs["16"]) == 2  # semifinals, seeds 1 & 2 enter here
    assert len(playoffs["17"]) == 1  # final

    week16_teams = {t for pair in playoffs["16"] for t in pair}
    assert "seed_1" in week16_teams
    assert "seed_2" in week16_teams


def test_playoff_template_matches_module_constant():
    # generate() should hand back the documented template unchanged.
    schedule = generate(TEAMS)
    assert schedule["playoffs"] == PLAYOFF_TEMPLATE


# --- determinism + seed behavior --------------------------------------------

def test_generate_is_deterministic_given_same_team_order_and_no_seed():
    first = generate(TEAMS)
    second = generate(TEAMS)
    assert first == second


def test_generate_is_deterministic_given_same_seed():
    first = generate(TEAMS, seed=42)
    second = generate(TEAMS, seed=42)
    assert first == second


def test_generate_with_seed_still_satisfies_all_constraints():
    schedule = generate(TEAMS, seed="draft-day-2026")
    regular = schedule["regular_season"]
    for week, pairs in regular.items():
        appearances = [team for pair in pairs for team in pair]
        assert set(appearances) == set(TEAMS)
        assert len(appearances) == 12

    seen_pairs = [frozenset(p) for w in range(1, 12) for p in regular[str(w)]]
    assert len(seen_pairs) == len(set(seen_pairs)) == 66


def test_different_seeds_can_produce_different_orderings():
    # Not a strict correctness requirement, but pins down that --seed
    # actually does something rather than being silently ignored.
    a = generate(TEAMS, seed=1)
    b = generate(TEAMS, seed=2)
    assert a["regular_season"]["1"] != b["regular_season"]["1"]


# --- input validation ---------------------------------------------------

def test_generate_rejects_wrong_team_count():
    with pytest.raises(ValueError):
        generate(TEAMS[:11])


def test_generate_rejects_duplicate_teams():
    bad = TEAMS[:11] + [TEAMS[0]]
    with pytest.raises(ValueError):
        generate(bad)

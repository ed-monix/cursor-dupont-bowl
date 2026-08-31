"""Pure schedule generator for DuPont Bowl (PLAN.md §2, TASKS.md 2.3).

`generate()` is the only function downstream code should need; `scripts/
schedule.py` is a thin CLI wrapper that calls it and writes the result to
`state/schedule.json`.

Format (12 teams, PLAN.md §2):

- Weeks 1-14 regular season, weeks 15-17 playoffs (6-team bracket, seeds 1-2
  byes).

Algorithm - circle method (a.k.a. polygon method) for round-robin scheduling:

    Fix team[0] in place; arrange the remaining 11 teams around it. Each
    round, pair position i with position (11 - i) for i in 0..5 -- that's 6
    pairs covering all 12 teams. Then rotate every team except team[0] one
    position (team[-1] moves to position 1, everyone else shifts up). Repeat
    for 11 rounds.

    This is the standard construction for a single round-robin over an even
    number of teams: it produces exactly n-1 = 11 rounds of n/2 = 6 pairs
    each, and every one of the C(12, 2) = 66 possible pairs appears in
    exactly one round. That combinatorial guarantee -- not a repeat-check
    loop -- is what satisfies the "no repeat opponent before week 12"
    constraint: weeks 1-11 ARE the 66 unique pairs, one per week, by
    construction, so there is nothing left to deduplicate.

Weeks 12-14 (regular season continues past the single round-robin, where
repeats are explicitly allowed by the ticket) reuse weeks 1-3's pairings
verbatim, in order -- week 12 == week 1's matchups, week 13 == week 2's,
week 14 == week 3's. Documented here since it's a real choice: any repeat
assignment for 12-14 is legal per the AC, this one is simplest and keeps the
early-season pairings evenly reused rather than concentrating repeats on a
handful of teams.

`schedule.json` shape (the data contract downstream `score_week.py` and
`scoreboard.py` read)::

    {
      "regular_season": {
        "1": [["team_a", "team_b"], ...6 pairs, 12 distinct teams...],
        ...
        "14": [...]
      },
      "playoffs": {
        "15": [["seed_3", "seed_6"], ["seed_4", "seed_5"]],
        "16": [["seed_1", "winner_15_2"], ["seed_2", "winner_15_1"]],
        "17": [["winner_16_1", "winner_16_2"]]
      }
    }

Playoff template: seeds are not known until standings finalize at the end of
week 14, so weeks 15-17 are templated by seed / by-reference-to-prior-game
placeholder rather than by team slug:

- Week 15 (quarterfinals): seed_3 v seed_6, seed_4 v seed_5. Seeds 1 and 2
  are absent -- that's their first-round bye.
- Week 16 (semifinals): fixed (non-reseeded) bracket -- seed_1 plays the
  winner of the 4-v-5 game (winner_15_2, the second week-15 pairing above),
  seed_2 plays the winner of the 3-v-6 game (winner_15_1). This is the
  standard "1 seed avoids the highest remaining seed's mirror" fixed bracket;
  it does not dynamically re-seed survivors by record, which would require
  runtime data this template doesn't have.
- Week 17 (final): winner_16_1 v winner_16_2, in the same left-to-right order
  as the week 16 pairings above.

Whatever resolves "winner_15_1" etc. into an actual team slug is the job of
whatever plays week 16/17 (`score_week.py` / the commissioner run), not this
generator -- this module only ever emits the template.
"""

from __future__ import annotations

import random

REGULAR_SEASON_WEEKS = 14
SINGLE_ROUND_ROBIN_WEEKS = 11  # weeks 1-11: the 66 unique pairs, no repeats
TEAM_COUNT = 12

PLAYOFF_TEMPLATE = {
    "15": [["seed_3", "seed_6"], ["seed_4", "seed_5"]],
    "16": [["seed_1", "winner_15_2"], ["seed_2", "winner_15_1"]],
    "17": [["winner_16_1", "winner_16_2"]],
}


def _circle_method_rounds(teams):
    """Return 11 rounds (lists of pairs) covering every pair exactly once.

    `teams` must have an even length (12, in practice). Standard circle
    method: teams[0] stays fixed; the rest rotate one step per round.
    """
    n = len(teams)
    arr = list(teams)
    rounds = []
    for _ in range(n - 1):
        pairs = [[arr[i], arr[n - 1 - i]] for i in range(n // 2)]
        rounds.append(pairs)
        # Rotate everyone except arr[0]: last element moves to index 1,
        # everything else shifts up by one.
        arr = [arr[0], arr[-1]] + arr[1:-1]
    return rounds


def generate(team_order, seed=None):
    """Build the full schedule structure. Pure function -- no file I/O.

    Args:
        team_order: list of 12 unique team slugs (str). This is the order
            teams are seated around the round-robin circle; it does not need
            to be a draft order or any particular order, but it fully
            determines the pairings (see `seed` below).
        seed: optional int/str/etc. accepted by `random.Random`. When given,
            a copy of `team_order` is shuffled with `random.Random(seed)`
            before generating -- e.g. to turn a draft-day randomized team
            order into a schedule without the caller having to pre-shuffle
            it themselves. Omit (None, the default) to use `team_order` as
            given, unshuffled.

    Returns a dict shaped like the module docstring's `schedule.json`
    example: {"regular_season": {"1": [...], ..., "14": [...]},
    "playoffs": {"15": [...], "16": [...], "17": [...]}}.

    Deterministic: the same (team_order, seed) always produces the same
    result -- no hidden global state, no wall-clock/OS randomness.
    """
    if len(team_order) != TEAM_COUNT:
        raise ValueError(f"expected {TEAM_COUNT} teams, got {len(team_order)}")
    if len(set(team_order)) != TEAM_COUNT:
        raise ValueError(f"team_order contains duplicates: {team_order!r}")

    order = list(team_order)
    if seed is not None:
        random.Random(seed).shuffle(order)

    rounds = _circle_method_rounds(order)  # 11 rounds, weeks 1-11
    assert len(rounds) == SINGLE_ROUND_ROBIN_WEEKS

    regular_season = {str(week): pairs for week, pairs in enumerate(rounds, start=1)}

    # Weeks 12-14: repeat weeks 1-3's pairings verbatim (see module
    # docstring). Repeats are only legal from week 12 on.
    for week, source_week in zip((12, 13, 14), (1, 2, 3)):
        regular_season[str(week)] = [
            list(pair) for pair in regular_season[str(source_week)]
        ]

    assert len(regular_season) == REGULAR_SEASON_WEEKS

    playoffs = {week: [list(pair) for pair in pairs] for week, pairs in PLAYOFF_TEMPLATE.items()}

    return {"regular_season": regular_season, "playoffs": playoffs}

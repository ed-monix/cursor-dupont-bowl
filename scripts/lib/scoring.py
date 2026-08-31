"""Fantasy scoring engine for DuPont Bowl.

Pure, stdlib-only functions that turn raw stat lines into fantasy points
using a Sleeper-style scoring config (see config/scoring.default.json /
config/scoring.json). No I/O, no network — callers load the JSON files and
pass in plain dicts.

Data contracts (see PLAN.md §8):
- `scoring`: a flat {stat_key: points_per_unit} map, Sleeper `scoring_settings`
  keys verbatim (pass_yd, pass_td, rec, fgm_20_29, pts_allow_14_20, ...).
- `stat_line`: a flat {stat_key: count} map for one player for one week.
- `roster`: a teams/*/roster.json object —
  {"team": ..., "faab_remaining": ..., "starters": {slot: player_id|None},
   "bench": [...], "ir": [...]}.
- `stats`: {player_id: stat_line} for one week.
"""

from __future__ import annotations

# DST "points allowed" tiers, keyed by Sleeper's scoring key, in ascending
# order of the point total they cover. Upper bound is inclusive; the last
# tier (35+) has no upper bound.
_PTS_ALLOW_TIERS: list[tuple[str, float | None]] = [
    ("pts_allow_0", 0),
    ("pts_allow_1_6", 6),
    ("pts_allow_7_13", 13),
    ("pts_allow_14_20", 20),
    ("pts_allow_21_27", 27),
    ("pts_allow_28_34", 34),
    ("pts_allow_35p", None),  # 35+
]

# The set of pre-bucketed flag keys, so the numeric `pts_allow` path can
# suppress them and avoid double-counting if a stat line (incorrectly)
# carries both forms at once.
_PTS_ALLOW_TIER_KEYS = frozenset(key for key, _ in _PTS_ALLOW_TIERS)


def _pts_allow_tier_key(points_allowed: float) -> str:
    """Map a numeric points-allowed value to its Sleeper tier key."""
    for key, upper in _PTS_ALLOW_TIERS:
        if upper is None or points_allowed <= upper:
            return key
    # Unreachable: the last tier has upper=None and always matches.
    raise AssertionError("unreachable")


def score_player(stat_line: dict, scoring: dict) -> float:
    """Score a single player's stat line against a scoring config.

    For every key in `stat_line` that also exists in `scoring`, adds
    stat_value * scoring_value. Keys absent from `scoring` are ignored.

    DST points-allowed is special-cased: a stat line may express it either
    as a numeric `pts_allow` (e.g. {"pts_allow": 17}) or as a pre-bucketed
    flag (e.g. {"pts_allow_14_20": 1}).
      - Numeric form: mapped to the correct tier key and that tier's
        scoring value is added exactly once (not multiplied by the raw
        points-allowed number — the tier value itself is the whole bonus).
      - Pre-bucketed form: treated like any other ordinary multiplier key
        (value * scoring_value), so a count of 1 gives the tier's full
        value, matching the numeric form.
      - If (unexpectedly) both forms are present in the same stat line,
        the numeric form wins and the pre-bucketed tier keys are ignored,
        so the tier bonus is never counted twice.
    """
    total = 0.0

    numeric_pts_allowed = stat_line.get("pts_allow")
    if numeric_pts_allowed is not None:
        tier_key = _pts_allow_tier_key(numeric_pts_allowed)
        total += scoring.get(tier_key, 0.0)

    for key, value in stat_line.items():
        if key == "pts_allow":
            continue  # handled above; not itself a scoring key
        if numeric_pts_allowed is not None and key in _PTS_ALLOW_TIER_KEYS:
            continue  # avoid double-counting against the numeric tier bonus
        if key in scoring:
            total += value * scoring[key]

    return float(total)


def score_lineup(roster: dict, stats: dict, scoring: dict) -> dict:
    """Score a roster's starters for one week.

    Returns {player_id: points, ..., "total": points_sum}. Only starters
    are scored (bench/ir are ignored). A starter slot holding `None`
    (unfilled) contributes 0 and is simply omitted from the result dict —
    there is no player_id to key it by.

    If a starter has no entry in `stats`, they are treated as scoring 0
    (an empty stat line), same as a bye/no-game player.
    """
    starters = roster.get("starters", {})
    result: dict = {}
    total = 0.0

    for player_id in starters.values():
        if player_id is None:
            continue
        stat_line = stats.get(player_id, {})
        pts = score_player(stat_line, scoring)
        result[player_id] = pts
        total += pts

    result["total"] = total
    return result

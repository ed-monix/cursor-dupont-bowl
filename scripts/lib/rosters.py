"""Roster load/save + legality validation for DuPont Bowl.

Data contracts (PLAN.md §8, fixed — do not change without a human decision):

    teams/*/roster.json:
        {"team": str, "faab_remaining": int,
         "starters": {slot: player_id | null, ...},
         "bench": [player_id, ...], "ir": [player_id, ...]}

    state/players.json:
        {player_id: {"name": str, "pos": str, "team": str,
                      "status": str, "injury": str | null}, ...}

Standard roster shape (PLAN.md §2), used whenever `config/roster.json`
has not been synced from Sleeper yet:

    QB, RB, RB, WR, WR, TE, FLEX (RB/WR/TE), K, DEF, 6 BN, 1 IR.

`roster_config`, where accepted, is an optional dict shaped like::

    {"starters": {slot: [allowed_pos, ...], ...},
     "bench_slots": int, "ir_slots": int}

Any key it omits falls back to the standard shape above. Passing None (the
default everywhere) uses the standard shape outright — this is the expected
mode until `config/roster.json` exists.

`config/roster.json` itself (as written by sync_sleeper.py) is a different,
flatter shape -- `{"roster_positions": [str, ...], "settings": {...}}` --
and is NOT accepted directly as `roster_config`. Convert it first with
`roster_config_from_league()` below.

Transaction shapes accepted by `apply_transaction`:

    {"type": "add", "player": id, "to": "bench" | "ir" | <starter slot>,
     "drop": id (optional)}
        Add `player` to the roster at `to`. If `drop` is given, that player
        is removed first (e.g. to free the starter slot being targeted, or
        just to make bench room). Adding into an already-occupied starter
        slot without dropping its occupant is rejected.

    {"type": "drop", "player": id}
        Remove `player` from wherever it sits (starter slot -> null, bench
        or ir -> removed from the list).

    {"type": "trade", "out": [id, ...], "in": [id, ...]}
        Remove every id in `out` from the roster, then add every id in `in`
        onto the bench. Rejected if any `out` id isn't on the roster, any
        `in` id is already on the roster, or the resulting bench would
        exceed the bench limit.

`apply_transaction` always works on a deep copy: the resulting roster is
validated with `validate_roster` before being returned, and on any failure
a `ValueError` is raised and the *input* roster object is left untouched
(nothing is applied, no partial writes).
"""

from __future__ import annotations

import copy
import json

from lib.scoring import score_player

DEFAULT_STARTER_SLOTS = {
    "QB": {"QB"},
    "RB1": {"RB"},
    "RB2": {"RB"},
    "WR1": {"WR"},
    "WR2": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "K": {"K"},
    "DEF": {"DEF"},
}
DEFAULT_BENCH_LIMIT = 6
DEFAULT_IR_LIMIT = 1


_FLEX_ELIGIBILITY = {
    "FLEX": ["RB", "WR", "TE"],
    "SUPER_FLEX": ["QB", "RB", "WR", "TE"],
    "WRRB_FLEX": ["RB", "WR"],
    "REC_FLEX": ["WR", "TE"],
}


def roster_config_from_league(league_cfg):
    """Adapt `config/roster.json` (as written by sync_sleeper.py) into the
    `roster_config` shape `_starter_slots`/`_bench_limit`/`_ir_limit` (and
    therefore `validate_roster`/`validate_lineup`/`apply_transaction`/
    `best_legal_lineup`) already consume::

        {"starters": {slot: [allowed_pos, ...], ...},
         "bench_slots": int, "ir_slots": int}

    Input is the raw dict `{"roster_positions": [str, ...], "settings": {...}}`
    (PLAN.md §8). `settings` is accepted but not read -- only
    `roster_positions` maps to the starters/bench/ir shape.

    `roster_positions` is a flat, ordered list of Sleeper roster slot
    tokens, one per roster spot. It is walked in order and split three ways:

    - A single-position token (QB, RB, WR, TE, K, DEF, or any other
      unrecognized token) becomes a starter slot named after itself, with
      that position as its sole eligibility (`[token]`). Repeated tokens
      get numeric suffixes in the order encountered: the first RB -> RB1,
      the second -> RB2, etc.; a lone (non-repeated) token keeps its bare
      name (e.g. QB -> QB, not QB1).
    - A recognized flex token becomes a starter slot (numbered the same
      way on repeats) whose eligibility is looked up in
      `_FLEX_ELIGIBILITY`: FLEX -> [RB, WR, TE], SUPER_FLEX ->
      [QB, RB, WR, TE], WRRB_FLEX -> [RB, WR], REC_FLEX -> [WR, TE]. Any
      other multi-flex-shaped token Sleeper might send is not specially
      recognized here, so it falls through to the "unknown token" rule
      below -- which for a flex-sounding name is exactly the safe
      default (RB/WR/TE) requested for unrecognized multi-flex tokens.
    - `BN` increments `bench_slots` and `IR` increments `ir_slots`; neither
      becomes a starter slot. `TAXI` is recognized and ignored (no taxi
      squad concept in this league). Any other unrecognized *non-flex*
      single token still becomes its own one-eligibility starter slot per
      the first bullet, since there is no separate "unknown non-starter"
      category to fall into.

    Pure, stdlib only. Returns a plain dict; does not mutate `league_cfg`.
    """
    starter_slots = {}
    seen_counts = {}
    bench_slots = 0
    ir_slots = 0

    positions = league_cfg.get("roster_positions") or []

    # First pass: count occurrences of each starter-producing token so a
    # token that appears exactly once keeps its bare name (QB, not QB1)
    # while a repeated one gets numbered from 1.
    total_counts = {}
    for token in positions:
        if token in ("BN", "IR", "TAXI"):
            continue
        total_counts[token] = total_counts.get(token, 0) + 1

    for token in positions:
        if token == "BN":
            bench_slots += 1
            continue
        if token == "IR":
            ir_slots += 1
            continue
        if token == "TAXI":
            continue

        seen_counts[token] = seen_counts.get(token, 0) + 1
        if total_counts[token] > 1:
            slot_name = f"{token}{seen_counts[token]}"
        else:
            slot_name = token

        if token in _FLEX_ELIGIBILITY:
            eligible = list(_FLEX_ELIGIBILITY[token])
        elif token in ("QB", "RB", "WR", "TE", "K", "DEF"):
            eligible = [token]
        else:
            # Unknown token: multi-flex-shaped names fall back to the
            # standard RB/WR/TE flex; anything else is treated as its own
            # single eligible position.
            eligible = ["RB", "WR", "TE"] if "FLEX" in token else [token]

        starter_slots[slot_name] = eligible

    return {
        "starters": starter_slots,
        "bench_slots": bench_slots,
        "ir_slots": ir_slots,
    }


def _starter_slots(roster_config):
    """slot -> set(eligible positions), from roster_config or the default."""
    if roster_config and roster_config.get("starters"):
        return {
            slot: set(positions)
            for slot, positions in roster_config["starters"].items()
        }
    return DEFAULT_STARTER_SLOTS


def _bench_limit(roster_config):
    if roster_config and roster_config.get("bench_slots") is not None:
        return roster_config["bench_slots"]
    return DEFAULT_BENCH_LIMIT


def _ir_limit(roster_config):
    if roster_config and roster_config.get("ir_slots") is not None:
        return roster_config["ir_slots"]
    return DEFAULT_IR_LIMIT


def load_roster(path):
    """Load a teams/*/roster.json file into a dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_roster(roster, path):
    """Write a roster dict as JSON with stable (sorted-key) formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, sort_keys=True)
        f.write("\n")


def slot_position_ok(slot, pos, roster_config=None):
    """True if a player at position `pos` may occupy starter slot `slot`."""
    slots = _starter_slots(roster_config)
    if slot not in slots:
        return False
    return pos in slots[slot]


def validate_roster(roster, players, roster_config=None):
    """Structural + legality checks for a single team's roster.

    Checks: every expected starter slot key is present (its value may be
    None -- an empty slot is legal at the roster level, e.g. bye weeks or
    before a lineup is set; see validate_lineup for "must be filled");
    any filled slot holds a real, position-eligible player; no player id
    appears more than once anywhere on the roster (starters/bench/ir);
    faab_remaining >= 0; bench and ir sizes within their limits.

    Returns (ok: bool, errors: list[str]).
    """
    errors = []

    starters = roster.get("starters")
    if not isinstance(starters, dict):
        errors.append("roster missing 'starters' dict")
        starters = {}

    slots = _starter_slots(roster_config)
    seen_ids = {}

    for slot, allowed_positions in slots.items():
        if slot not in starters:
            errors.append(f"missing starter slot: {slot}")
            continue
        pid = starters[slot]
        if pid is None:
            continue
        if pid not in players:
            errors.append(f"slot {slot}: player {pid} not found in players lookup")
            continue
        pos = players[pid].get("pos")
        if pos not in allowed_positions:
            errors.append(
                f"slot {slot}: player {pid} position {pos} not eligible "
                f"(allowed {sorted(allowed_positions)})"
            )
        if pid in seen_ids:
            errors.append(f"duplicate player {pid} in slots {seen_ids[pid]} and {slot}")
        else:
            seen_ids[pid] = slot

    bench = roster.get("bench", [])
    if not isinstance(bench, list):
        errors.append("roster 'bench' must be a list")
        bench = []
    ir = roster.get("ir", [])
    if not isinstance(ir, list):
        errors.append("roster 'ir' must be a list")
        ir = []

    bench_limit = _bench_limit(roster_config)
    ir_limit = _ir_limit(roster_config)
    if len(bench) > bench_limit:
        errors.append(f"bench has {len(bench)} players, limit is {bench_limit}")
    if len(ir) > ir_limit:
        errors.append(f"ir has {len(ir)} players, limit is {ir_limit}")

    for pid in bench:
        if pid in seen_ids:
            errors.append(f"duplicate player {pid} in {seen_ids[pid]} and bench")
        else:
            seen_ids[pid] = "bench"
    for pid in ir:
        if pid in seen_ids:
            errors.append(f"duplicate player {pid} in {seen_ids[pid]} and ir")
        else:
            seen_ids[pid] = "ir"

    faab = roster.get("faab_remaining")
    if not isinstance(faab, (int, float)) or isinstance(faab, bool) or faab < 0:
        errors.append(f"faab_remaining must be >= 0 (got {faab!r})")

    return (len(errors) == 0, errors)


# Injury designations that bar a player from a starting slot. "Questionable" is
# deliberately NOT here: a questionable player is a football judgment and taking
# it away would neuter the GMs -- Tony Soprano started a questionable Kyler
# Murray in week 2 as a disciplinary message to Bo Nix, which is terrible
# management and entirely his right. These four are different. A player who is
# Out, Doubtful, on IR or suspended is not dressing, so starting him is not a
# gamble, it is an empty slot scoring zero, and the fallback should fill it.
CANNOT_START_INJURY = frozenset({"out", "doubtful", "ir", "suspended"})


def injury_bars_starting(player: dict) -> bool:
    """Is this player's designation one that means he will not play at all?"""
    if not isinstance(player, dict):
        return False
    for field in ("injury", "status"):
        value = (player.get(field) or "").strip().lower()
        if value in CANNOT_START_INJURY:
            return True
    return False


def validate_lineup(roster, players, roster_config=None):
    """Game-day lineup check: every starter slot filled, position-eligible,
    not ruled out, and no player started in two slots at once.

    Returns (ok: bool, errors: list[str]).
    """
    errors = []
    starters = roster.get("starters", {}) or {}
    slots = _starter_slots(roster_config)
    seen = {}

    for slot in slots:
        pid = starters.get(slot)
        if pid is None:
            errors.append(f"slot {slot} is empty")
            continue
        if pid not in players:
            errors.append(f"slot {slot}: player {pid} not found in players lookup")
            continue
        pos = players[pid].get("pos")
        if not slot_position_ok(slot, pos, roster_config):
            errors.append(f"slot {slot}: player {pid} position {pos} not eligible")
        if injury_bars_starting(players[pid]):
            tag = players[pid].get("injury") or players[pid].get("status")
            errors.append(f"slot {slot}: player {pid} is {tag} and cannot start")
        if pid in seen:
            errors.append(
                f"player {pid} started in multiple slots ({seen[pid]} and {slot})"
            )
        else:
            seen[pid] = slot

    return (len(errors) == 0, errors)


def duplicate_players_across_teams(rosters):
    """Given a list of roster dicts, return sorted player_ids rostered on
    more than one team league-wide."""
    counts = {}
    for roster in rosters:
        on_this_team = set()
        for pid in (roster.get("starters") or {}).values():
            if pid is not None:
                on_this_team.add(pid)
        for pid in roster.get("bench", []) or []:
            on_this_team.add(pid)
        for pid in roster.get("ir", []) or []:
            on_this_team.add(pid)
        for pid in on_this_team:
            counts[pid] = counts.get(pid, 0) + 1
    return sorted(pid for pid, n in counts.items() if n > 1)


def _find_player(roster, player_id):
    """Return ('starters', slot) | ('bench', None) | ('ir', None) | None."""
    for slot, pid in (roster.get("starters") or {}).items():
        if pid == player_id:
            return ("starters", slot)
    if player_id in (roster.get("bench") or []):
        return ("bench", None)
    if player_id in (roster.get("ir") or []):
        return ("ir", None)
    return None


def _remove_player(roster, player_id):
    """Remove player_id from roster in place. Raises ValueError if absent."""
    loc = _find_player(roster, player_id)
    if loc is None:
        raise ValueError(f"player {player_id} not found on roster")
    kind, slot = loc
    if kind == "starters":
        roster["starters"][slot] = None
    elif kind == "bench":
        roster["bench"].remove(player_id)
    elif kind == "ir":
        roster["ir"].remove(player_id)


def apply_transaction(roster, txn, players, roster_config=None):
    """Apply one add/drop/trade transaction and return a NEW, valid roster.

    Never mutates `roster`: a deep copy is built and validated, and only
    that copy is touched or returned. On any illegal result -- unknown
    player, occupied slot, overflowed bench/ir, invalid resulting roster
    -- raises ValueError with a descriptive message and the input roster
    is guaranteed unchanged.
    """
    new_roster = copy.deepcopy(roster)
    ttype = txn.get("type")

    if ttype == "add":
        if "player" not in txn:
            raise ValueError("add transaction requires 'player'")
        player_id = txn["player"]
        drop_id = txn.get("drop")
        to = txn.get("to", "bench")

        if drop_id is not None:
            _remove_player(new_roster, drop_id)

        if _find_player(new_roster, player_id) is not None:
            raise ValueError(f"player {player_id} already on roster")

        if to == "bench":
            new_roster.setdefault("bench", []).append(player_id)
        elif to == "ir":
            new_roster.setdefault("ir", []).append(player_id)
        else:
            slots = _starter_slots(roster_config)
            if to not in slots:
                raise ValueError(f"unknown target slot: {to}")
            current = (new_roster.get("starters") or {}).get(to)
            if current is not None:
                raise ValueError(
                    f"slot {to} already occupied by {current}; drop that player first"
                )
            new_roster.setdefault("starters", {})[to] = player_id

    elif ttype == "drop":
        if "player" not in txn:
            raise ValueError("drop transaction requires 'player'")
        _remove_player(new_roster, txn["player"])

    elif ttype == "trade":
        out_ids = txn.get("out", [])
        in_ids = txn.get("in", [])
        for pid in out_ids:
            _remove_player(new_roster, pid)
        for pid in in_ids:
            if _find_player(new_roster, pid) is not None:
                raise ValueError(f"player {pid} already on roster")
            new_roster.setdefault("bench", []).append(pid)

    else:
        raise ValueError(f"unknown transaction type: {ttype!r}")

    ok, errors = validate_roster(new_roster, players, roster_config)
    if not ok:
        raise ValueError("resulting roster is invalid: " + "; ".join(errors))

    return new_roster


def best_legal_lineup(roster, players, projections, scoring, roster_config=None,
                      frozen_starters=None):
    """Deterministic lineup fallback: the highest-projected legal lineup
    (PLAN.md §4, TASKS.md 3.3) built purely from the roster already on
    hand -- no network, no agent call.

    `frozen_starters` is an optional `{slot: player_id}` of slots that must
    stay put (already locked by an earlier `/lineups` window or a kicked
    NFL game). Those players are seated first and removed from the pool.

    Player pool: every player currently in a (non-null) starter slot plus
    everyone on the bench. `ir` is excluded -- IR players are injured /
    ineligible and are never auto-started. Each pool player's projected
    points is `score_player(projections.get(pid, {}), scoring)`; a player
    with no projection entry scores 0.0 rather than raising.

    Greedy fill, in slot order QB, RB1, RB2, WR1, WR2, TE, K, DEF, then
    FLEX last: each slot takes the highest-projected not-yet-used pool
    player eligible for it. This is optimal for the fixed slot structure
    -- every non-FLEX slot's eligible position is disjoint from every
    other non-FLEX slot's (a QB can never fill an RB slot, etc.), so
    filling them first can never take a player another non-FLEX slot
    needed. FLEX (RB/WR/TE) is filled last from whatever is left, which
    is exactly "the best remaining RB/WR/TE not already started" -- no
    swap between any two slots could raise the lineup's total.

    Ties in projected points are broken by ASCII/string sort of
    player_id (lower id wins), so the result is stable across runs given
    the same inputs.

    Returns a NEW roster dict (deep copy of `roster`): `starters` is
    fully replaced with the computed lineup, every pool player not
    started ends up on `bench`, and `ir` is carried over untouched. If
    the pool has no eligible player left for a required slot (e.g. no K
    survived to the pool), that slot is left `None` -- this function
    never raises for an incomplete pool; callers should run
    `validate_lineup` on the result if they need to know whether it's
    game-ready.
    """
    new_roster = copy.deepcopy(roster)
    slots = _starter_slots(roster_config)

    pool_ids = []
    for pid in (roster.get("starters") or {}).values():
        if pid is not None:
            pool_ids.append(pid)
    for pid in roster.get("bench", []) or []:
        pool_ids.append(pid)
    # de-dupe while keeping the pool a plain set of candidates -- a
    # player should never legitimately appear in both starters and
    # bench, but don't let a malformed roster double-count one.
    pool_ids = list(dict.fromkeys(pool_ids))

    def projected_points(pid):
        return score_player(projections.get(pid, {}) or {}, scoring)

    # Sort once: best projection first, lower player_id breaking ties.
    pool_sorted = sorted(pool_ids, key=lambda pid: (-projected_points(pid), pid))

    def position_of(pid):
        return players.get(pid, {}).get("pos")

    used = set()
    new_starters = {}
    for slot, pid in (frozen_starters or {}).items():
        if pid:
            new_starters[slot] = pid
            used.add(pid)

    def fill_slot(allowed_positions):
        for pid in pool_sorted:
            if pid in used:
                continue
            if position_of(pid) in allowed_positions:
                used.add(pid)
                return pid
        return None

    new_starters = dict(new_starters)
    # Non-FLEX slots first; FLEX last so it only draws leftover RB/WR/TE.
    flex_slots = [slot for slot, allowed in slots.items() if len(allowed) != 1]
    single_pos_slots = [slot for slot in slots if slot not in flex_slots]

    for slot in single_pos_slots:
        if slot not in new_starters:
            new_starters[slot] = fill_slot(slots[slot])
    for slot in flex_slots:
        if slot not in new_starters:
            new_starters[slot] = fill_slot(slots[slot])

    new_roster["starters"] = new_starters
    new_roster["bench"] = [pid for pid in pool_sorted if pid not in used]
    return new_roster

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


def validate_lineup(roster, players, roster_config=None):
    """Game-day lineup check: every starter slot filled, position-eligible,
    and no player started in two slots at once.

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

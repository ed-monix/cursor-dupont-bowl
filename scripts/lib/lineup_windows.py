"""Merge / freeze lineups across multiple in-week windows.

A GM always submits a full legal starting lineup. This module decides
which slots may actually change:

- A slot already recorded in `locked_slots` stays frozen.
- A slot whose NFL game has kicked off (`in_game` / `complete`) stays frozen.
- On window `early`, only early-slate slots (Tue–Sat games) become newly
  locked after the merge. Sunday/Monday slots are saved as the current
  declared lineup but remain editable on the `main` window.
- On window `main`, every still-unlocked slot is locked (Sun/Mon + anyone
  the early run missed).

Fallback lineups (`best_legal_lineup`) must also respect frozen slots:
swap only unlocked positions.
"""
from __future__ import annotations

from typing import Optional

from lib import nfl_slate


def locked_player_ids(lineup_entry: Optional[dict]) -> set:
    """Player ids that must stay in their starter slots."""
    if not lineup_entry:
        return set()
    locked = lineup_entry.get("locked_slots") or {}
    ids = set()
    for slot, info in locked.items():
        if isinstance(info, dict):
            pid = info.get("player_id")
        else:
            pid = info
        if pid:
            ids.add(pid)
    return ids


def slot_is_frozen(slot: str, lineup_entry: Optional[dict], player: Optional[dict],
                   by_team: dict) -> bool:
    """True if this starter slot cannot be changed this run."""
    if lineup_entry:
        locked = lineup_entry.get("locked_slots") or {}
        if slot in locked:
            return True
    if not player:
        return False
    nfl = player.get("nfl")
    game = nfl_slate.lookup_game(nfl, by_team)
    return nfl_slate.game_has_kicked(game)


def merge_lineup(
    existing: Optional[dict],
    proposed_starters: dict,
    window: str,
    resolved_by_id: dict,
    by_team: dict,
    justification: str = "",
    fallback: bool = False,
) -> dict:
    """Return the new lineups.json entry for one team.

    `resolved_by_id` maps player_id -> league-board row (needs `nfl`).
    `proposed_starters` is `{slot: player_id}` from the GM (or fallback).
    """
    if window not in nfl_slate.WINDOWS:
        raise ValueError(f"unknown lineup window {window!r}; use {nfl_slate.WINDOWS}")

    prev = existing or {}
    prev_starters = dict(prev.get("starters") or {})
    locked_slots = dict(prev.get("locked_slots") or {})
    windows_run = list(prev.get("windows_run") or [])
    justifications = dict(prev.get("justifications") or {})
    if prev.get("justification") and "legacy" not in justifications:
        justifications["legacy"] = prev["justification"]

    merged = dict(prev_starters)
    # Start from previous starters so an omitted unlocked slot doesn't blank.
    for slot, pid in (proposed_starters or {}).items():
        current_pid = prev_starters.get(slot)
        current_row = resolved_by_id.get(current_pid) if current_pid else None
        if slot_is_frozen(slot, prev, current_row, by_team):
            continue
        merged[slot] = pid

    # Newly lock slots that belong to this window (or any kicked game).
    for slot, pid in merged.items():
        if slot in locked_slots:
            continue
        row = resolved_by_id.get(pid) if pid else None
        nfl = (row or {}).get("nfl")
        game = nfl_slate.lookup_game(nfl, by_team)
        kicked = nfl_slate.game_has_kicked(game)
        game_window = nfl_slate.window_for_game(game) if game else "main"
        should_lock = kicked or window == "main" or game_window == window
        if should_lock and pid:
            locked_slots[slot] = {
                "player_id": pid,
                "window": window,
                "nfl": nfl,
                "game_date": (game or {}).get("date"),
                "kicked": kicked,
            }

    if window not in windows_run:
        windows_run.append(window)
    justifications[window] = justification or justifications.get(window, "")

    return {
        "starters": merged,
        "locked_slots": locked_slots,
        "windows_run": windows_run,
        "justification": justification or prev.get("justification") or "",
        "justifications": justifications,
        "fallback": bool(fallback) or bool(prev.get("fallback")),
    }


def freeze_violations(
    existing: Optional[dict],
    proposed_starters: dict,
    resolved_by_id: dict,
    by_team: dict,
) -> list:
    """Human-readable errors if the GM tried to move a frozen slot."""
    errors = []
    prev = existing or {}
    prev_starters = prev.get("starters") or {}
    for slot, new_pid in (proposed_starters or {}).items():
        old_pid = prev_starters.get(slot)
        if new_pid == old_pid:
            continue
        current_row = resolved_by_id.get(old_pid) if old_pid else None
        if slot_is_frozen(slot, prev, current_row, by_team):
            errors.append(
                f"slot {slot} is frozen (locked or game already kicked); "
                f"keep {old_pid}, cannot start {new_pid}"
            )
    return errors

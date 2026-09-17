"""Apply one /lineups window. Scripts decide freeze, merge, and fallback.

GMs submit a full lineup JSON. This module:

- validates slot legality (``validate_lineup``)
- refuses to move frozen slots (locked earlier, or NFL game already kicked)
- on illegal submissions, builds ``best_legal_lineup(..., frozen_starters=)``
- merges via ``lineup_windows.merge_lineup``

A legal lineup that tries to move a frozen slot is **not** a fallback: the
merge keeps the locked player. Fallback (``fallback: true``, Hall of Shame)
is only for illegal / missing submissions after retry.
"""
from __future__ import annotations

import copy
from typing import Optional

from lib import nfl_slate
from lib.lineup_windows import freeze_violations, merge_lineup, slot_is_frozen
from lib.rosters import best_legal_lineup, validate_lineup


def resolved_by_id(players: dict, board: Optional[dict] = None) -> dict:
    """player_id -> row with at least ``nfl`` (league-board wins)."""
    out = {}
    for pid, info in (players or {}).items():
        if not isinstance(info, dict):
            continue
        out[pid] = {
            "id": pid,
            "name": info.get("name"),
            "pos": info.get("pos"),
            "nfl": info.get("team") or info.get("nfl"),
            "status": info.get("status"),
            "injury": info.get("injury"),
            "proj_pts": info.get("proj_pts"),
        }
    for side in (board or {}).values():
        if not isinstance(side, dict):
            continue
        rows = list((side.get("starters") or {}).values())
        rows.extend(side.get("bench") or [])
        rows.extend(side.get("ir") or [])
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                out[row["id"]] = row
    return out



def reconciled_bench(roster: dict, new_starters: dict) -> list:
    """The bench that goes with `new_starters`, conserving the rostered set.

    Setting `starters` alone is not a lineup change, it is a leak. Whoever was
    promoted is still sitting on the bench (a duplicate the validator rejects)
    and whoever was demoted is on no list at all (silently dropped from the
    roster). `week 01: apply lineups-main` did exactly that to five of twelve
    teams -- costanza lost Baker Mayfield and Rachaad White -- and nothing
    noticed until FAAB validated a roster three weeks of league time later.

    So the bench is derived, never carried over: everyone the team held before
    (starters + bench), minus whoever is starting now. Surviving bench players
    keep their order and demoted starters are appended in slot order, so a
    no-op lineup leaves the file byte-identical. IR is not touched -- an IR
    player is not a lineup decision.
    """
    starting = {str(pid) for pid in (new_starters or {}).values() if pid}
    held = []
    for pid in (roster.get("bench") or []):
        held.append(str(pid))
    for _slot, pid in sorted((roster.get("starters") or {}).items()):
        if pid:
            held.append(str(pid))

    bench = []
    for pid in held:
        if pid not in starting and pid not in bench:
            bench.append(pid)
    return bench


def frozen_starters_map(
    existing: Optional[dict],
    roster: dict,
    resolved: dict,
    by_team: dict,
) -> dict:
    """Slots that fallback must not move."""
    frozen = {}
    starters = (existing or {}).get("starters") or (roster.get("starters") or {})
    for slot, pid in starters.items():
        if not pid:
            continue
        row = resolved.get(pid)
        if slot_is_frozen(slot, existing, row, by_team):
            frozen[slot] = pid
    return frozen


def apply_lineup_window(
    rosters: dict,
    players: dict,
    projections: dict,
    scoring: dict,
    decisions: dict,
    window: str,
    games: list,
    existing_lineups: Optional[dict] = None,
    board: Optional[dict] = None,
) -> dict:
    """Pure apply of one window.

    ``decisions`` is ``{slug: {starters, justification}}``.
    Returns ``{lineups, rosters, report}``.
    """
    if window not in nfl_slate.WINDOWS:
        raise ValueError(f"unknown lineup window {window!r}; use {nfl_slate.WINDOWS}")

    by_team = nfl_slate.index_games_by_team(games)
    resolved = resolved_by_id(players, board)
    lineups_out = copy.deepcopy(existing_lineups) if existing_lineups else {}
    updated_rosters = copy.deepcopy(rosters)
    team_reports = []

    for slug, roster in sorted(updated_rosters.items()):
        existing = lineups_out.get(slug)
        canned = decisions.get(slug) if isinstance(decisions.get(slug), dict) else {}
        proposed = canned.get("starters")
        justification = canned.get("justification") or ""
        val_errors = []
        freeze_errs = []
        fallback = False
        candidate_starters = dict(roster.get("starters") or {})

        if not proposed:
            val_errors = ["no lineup submitted for this team"]
        else:
            candidate = copy.deepcopy(roster)
            candidate["starters"] = dict(proposed)
            ok, val_errors = validate_lineup(candidate, players)
            freeze_errs = freeze_violations(existing, proposed, resolved, by_team)
            candidate_starters = dict(proposed)
            if ok:
                val_errors = []

        if val_errors:
            fallback = True
            frozen = frozen_starters_map(existing, roster, resolved, by_team)
            candidate = best_legal_lineup(
                roster, players, projections, scoring, frozen_starters=frozen,
            )
            ok2, err2 = validate_lineup(candidate, players)
            if not ok2:
                raise ValueError(f"{slug} fallback lineup is still illegal: {err2}")
            candidate_starters = dict(candidate["starters"])
            justification = (
                "FALLBACK (highest-projected legal lineup): submitted lineup was "
                "illegal -- " + "; ".join(val_errors)
            )

        merged = merge_lineup(
            existing,
            candidate_starters,
            window,
            resolved,
            by_team,
            justification=justification,
            fallback=fallback,
        )
        new_roster = copy.deepcopy(roster)
        new_roster["starters"] = dict(merged["starters"])
        new_roster["bench"] = reconciled_bench(roster, merged["starters"])
        updated_rosters[slug] = new_roster
        lineups_out[slug] = merged
        team_reports.append({
            "team": slug,
            "fallback": bool(merged.get("fallback")),
            "locked_slots": sorted(merged.get("locked_slots") or {}),
            "freeze_violations": freeze_errs,
            "validation_errors": val_errors,
        })

    return {
        "lineups": lineups_out,
        "rosters": updated_rosters,
        "report": {"window": window, "teams": team_reports},
    }

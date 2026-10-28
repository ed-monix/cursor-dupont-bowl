#!/usr/bin/env python3
"""faab.py — FAAB waiver resolution for the Saturday roster run (TASKS.md 2.1).

Rules implemented (PLAN.md §4 step 4, config/league-rules.md "Waivers &
free agency"):

    - Blind FAAB, budget $100/season, min bid $0. Highest bid wins a
      contested player.
    - Tie on a player -> the team with the WORSE standing wins.
    - Each team submits an ORDERED list of claims (priority order); a
      team's own claims are processed in that order.
    - A team cannot win two claims that need the SAME drop player: once a
      claim consumes a drop, a later claim from the same team needing that
      same drop is skipped.
    - A claim whose drop player is already gone (not on that team's roster
      to begin with) is skipped.
    - Standalone drops (drops in the decision that are not tied to a claim)
      are applied for that team before its claims are checked for roster
      room. A standalone drop naming a player who is not on the roster is
      skipped and logged with the same reason as a claim drop of an absent
      player. Bid order, tiebreaks, budgets, and the already-rostered skip
      are fixed before any of these drops, so one team's drops do not
      change another team's resolution.
    - A claim for a player already on another team's roster is skipped
      (logged, not applied). It never enters the auction, so it cannot
      win, charge FAAB, or land on a second roster.
    - A won claim's bid is deducted from the team's remaining FAAB; a team
      can never be charged more than it has (a bid that would overspend the
      team's remaining budget is skipped, not applied).
    - Losers of a contested player: their claim fails (logged), no budget
      deducted.

Data shapes this module works with
-----------------------------------

``claims_by_team``: ``{team_slug: [claim, ...], ...}``. Each team's list is
its priority order (index 0 = highest priority). A claim is::

    {"add": player_id, "drop": player_id | None, "bid": int,
     "reasoning": str}          # "reasoning" is optional, carried through
                                 # to the transaction log for the recap.

``standings``: ``[team_slug, ...]`` ordered **worst -> best** (index 0 is
the worst record in the league, the last entry is the best). This is the
one tiebreak input FAAB resolution needs; it is *not* a full standings
object (see ``state/standings.json`` for that — build a worst->best slug
list from it before calling ``resolve_faab``). A team with no claims does
not need to appear in ``standings`` unless it ends up tied with another
team on a bid.

``rosters``: ``{team_slug: roster_dict, ...}`` in the ``teams/*/roster.json``
shape from ``lib.rosters`` (PLAN.md §8) — used to read each team's starting
``faab_remaining`` and to check whether a claimed drop player is actually on
that team's roster.

``players``: ``{player_id: {...}, ...}`` — ``state/players.json``, used only
to reject claims that add an unknown player id.

``drops_by_team``: optional ``{team_slug: [player_id, ...]}``. The decision's
standalone drops (``docs/schemas/saturday-decision.json`` ``drops``), not the
drop named on a claim. Omitted or empty leaves resolution unchanged.

Resolution report (``resolve_faab`` return value)
--------------------------------------------------

    {"claims": [
        {"team": str, "add": id, "drop": id | None, "bid": int,
         "reasoning": str | None, "status": "won" | "lost" | "skipped",
         "reason": str},
        ...
     ],
     "drops": [
        {"team": str, "player": id, "status": "applied" | "skipped",
         "reason": str},
        ...
     ],
     "remaining_budget": {team_slug: int, ...}}   # FAAB left after this run

``claims`` preserves team order (as given in ``claims_by_team``) and, within
a team, priority order — so the report reads the same way the claims were
submitted.

Apply step
----------

``resolve_faab`` is pure (no disk I/O). ``apply_won_claims`` takes its report
plus the same ``rosters``/``players`` and applies every standalone drop the
report marked ``"applied"`` before that team's won claims, then, for every
``"won"`` claim, calls ``lib.rosters.apply_transaction`` (add with drop, when
present) and builds one ``state/transactions.jsonl`` entry per applied drop
and per applied claim::

    {"timestamp": iso8601 str, "team": str, "action": "waiver_claim",
     "players": [add_id, drop_id?], "bid": int, "reasoning": str,
     "status": "applied"}   # conforms to docs/schemas/transaction-entry.json

It is also pure (returns updated rosters + entries; raises ValueError if a
"won" claim is somehow illegal, propagated straight from
``apply_transaction``). ``write_results`` is the thin disk-writing wrapper
the CLI uses.

CLI
---

    python scripts/faab.py --claims claims.json --standings standings.json \\
        --players state/players.json --rosters-dir teams \\
        [--roster-config config/roster.json] [--drops drops.json] \\
        [--report-out state/weeks/2026-w05/faab-report.json] \\
        [--transactions state/transactions.jsonl] [--dry-run]

``--dry-run`` writes the resolution report only; without it, won claims are
applied to ``teams/*/roster.json`` and appended to ``--transactions``.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.rosters import (  # noqa: E402
    _starter_slots, apply_transaction, roster_config_from_league, save_roster, validate_roster,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _standing_rank(team: str, standings: list[str]) -> int:
    """Lower rank = worse standing = wins ties. Raises ValueError if the
    team isn't in `standings` (every team with a contested bid must be)."""
    try:
        return standings.index(team)
    except ValueError:
        raise ValueError(
            f"team {team!r} has a contested claim but is missing from standings"
        ) from None


def _roster_has_player(roster: dict, player_id: str) -> bool:
    starters = (roster.get("starters") or {}).values()
    if player_id in starters:
        return True
    if player_id in (roster.get("bench") or []):
        return True
    if player_id in (roster.get("ir") or []):
        return True
    return False


def _other_roster_owner(rosters: dict, player_id, claiming_team: str):
    """Slug of another team that already rosters ``player_id``, or None.

    Checked against the rosters at the start of the run. A same-team add is
    not this case (``apply_transaction`` already rejects that). Team order is
    sorted so the logged owner is stable if a player is somehow on two clubs.
    """
    keys = {player_id}
    if player_id is not None:
        keys.add(str(player_id))
    for team in sorted(rosters):
        if team == claiming_team:
            continue
        roster = rosters.get(team) or {}
        for key in keys:
            if _roster_has_player(roster, key):
                return team
    return None


def _pick_winner(bids: list[tuple[str, dict]], standings: list[str]) -> tuple[str, dict]:
    """bids: [(team, claim), ...] all bidding on the same add player.
    Highest bid wins; ties broken by worse standing (lower rank index)."""
    def sort_key(item):
        team, claim = item
        return (-claim["bid"], _standing_rank(team, standings))

    ranked = sorted(bids, key=sort_key)
    return ranked[0]


def _apply_standalone_drops(team, drop_ids, base_roster, players, roster_config):
    """Apply drops that are not tied to a claim. Returns
    ``(roster, report_rows, dropped_ids)``.

    A drop naming a player who is not on the roster is skipped and logged
    with the same reason a claim drop of an absent player already uses.
    ``base_roster`` is not mutated. ``roster`` is ``base_roster`` itself when
    nothing was removed.
    """
    roster = base_roster
    rows = []
    dropped = []
    for drop_id in drop_ids or []:
        if not _roster_has_player(roster, drop_id):
            rows.append({
                "team": team,
                "player": drop_id,
                "status": "skipped",
                "reason": f"drop player {drop_id} not on roster (already gone)",
            })
            continue
        try:
            roster = apply_transaction(
                roster, {"type": "drop", "player": drop_id}, players, roster_config)
        except (ValueError, KeyError) as e:
            rows.append({
                "team": team,
                "player": drop_id,
                "status": "skipped",
                "reason": f"would leave an illegal roster: {e}",
            })
            continue
        dropped.append(drop_id)
        rows.append({
            "team": team,
            "player": drop_id,
            "status": "applied",
            "reason": "standalone drop",
        })
    return roster, rows, dropped


def resolve_faab(claims_by_team: dict, standings: list, rosters: dict,
                 players: dict, roster_config=None, drops_by_team=None) -> dict:
    """Pure FAAB resolution. See module docstring for all shapes. No I/O."""

    # --- Phase 1: bucket every claim by the player it adds, dropping
    # claims for unknown players out of the auction entirely (they can
    # never win) but still recording them as skipped in the report.
    # Standalone drops are not applied here. Who is rostered, and therefore
    # who may enter the auction, is the roster at the start of the run.
    bids_by_add: dict[str, list[tuple[str, dict]]] = {}
    unknown_claims: list[tuple[str, dict]] = []
    # Claims on a player another team already rosters never enter the
    # auction. Pulling them out here leaves bid order, tiebreaks, and
    # budgets for everyone else exactly as they were.
    rostered_claims: list[tuple[str, dict, str]] = []

    for team, claim_list in claims_by_team.items():
        for claim in claim_list:
            add_id = claim["add"]
            if add_id not in players:
                unknown_claims.append((team, claim))
                continue
            owner = _other_roster_owner(rosters, add_id, team)
            if owner is not None:
                rostered_claims.append((team, claim, owner))
                continue
            bids_by_add.setdefault(add_id, []).append((team, claim))

    # --- Phase 2: pick one winner per contested add id, purely by bid +
    # standings tiebreak. This is independent of team priority order.
    winner_of: dict[str, tuple[str, dict]] = {}
    for add_id, bids in bids_by_add.items():
        winner_of[add_id] = _pick_winner(bids, standings)

    # --- Phase 3: walk teams in submission order, each team's claims in
    # its own priority order, applying the sequential per-team rules
    # (drop consumption, budget) on top of the fixed winner assignment.
    report_claims = []
    report_drops = []
    remaining_budget = {
        team: rosters.get(team, {}).get("faab_remaining", 0) for team in claims_by_team
    }

    unknown_lookup = {id(claim): True for _, claim in unknown_claims}
    rostered_lookup = {id(claim): owner for _, claim, owner in rostered_claims}

    # A team can win more than one claim, and each changes its roster, so
    # legality has to be checked against the roster as it will actually be
    # when the claim lands — not against the roster it started the run with.
    working: dict = {}

    drops_by_team = drops_by_team or {}
    seen_teams = set()

    def _take_standalone_drops(team):
        """Ruling 2026-11: a team's own standalone drops land before its
        claims are checked for roster room. Other teams' rosters are not
        touched, and the auction above has already named a winner."""
        base = working.get(team, rosters.get(team, {}))
        roster_after, rows, dropped = _apply_standalone_drops(
            team, drops_by_team.get(team) or [], base, players, roster_config)
        report_drops.extend(rows)
        if dropped:
            working[team] = roster_after
        return set(dropped)

    for team, claim_list in claims_by_team.items():
        seen_teams.add(team)
        pre_dropped = _take_standalone_drops(team)
        consumed_drops: set = set()
        for claim in claim_list:
            add_id = claim["add"]
            drop_id = claim.get("drop")
            bid = claim["bid"]
            reasoning = claim.get("reasoning")
            entry = {
                "team": team,
                "add": add_id,
                "drop": drop_id,
                "bid": bid,
                "reasoning": reasoning,
            }

            if id(claim) in unknown_lookup:
                entry["status"] = "skipped"
                entry["reason"] = f"unknown player id: {add_id}"
                report_claims.append(entry)
                continue

            if id(claim) in rostered_lookup:
                owner = rostered_lookup[id(claim)]
                entry["status"] = "skipped"
                entry["reason"] = f"player {add_id} already rostered by {owner}"
                report_claims.append(entry)
                continue

            winner_team, winner_claim = winner_of[add_id]
            if winner_team != team or winner_claim is not claim:
                if winner_claim["bid"] == bid:
                    entry["status"] = "lost"
                    entry["reason"] = (
                        f"tied bid ${bid} for {add_id}; lost tiebreak to "
                        f"{winner_team} (worse standing wins)"
                    )
                else:
                    entry["status"] = "lost"
                    entry["reason"] = (
                        f"outbid on {add_id}: {winner_team} bid "
                        f"${winner_claim['bid']} (your bid ${bid})"
                    )
                report_claims.append(entry)
                continue

            # This claim holds the winning bid for add_id. Check whether it
            # can actually be applied.
            if drop_id is not None:
                if drop_id in consumed_drops:
                    entry["status"] = "skipped"
                    entry["reason"] = (
                        f"drop player {drop_id} already used by an earlier "
                        f"claim this run"
                    )
                    report_claims.append(entry)
                    continue
                # Original roster, plus anyone this team's standalone drops
                # already removed. A player who was never there, and a player
                # those drops already released, both use the existing skip.
                team_roster = rosters.get(team, {})
                if drop_id in pre_dropped or not _roster_has_player(team_roster, drop_id):
                    entry["status"] = "skipped"
                    entry["reason"] = f"drop player {drop_id} not on roster (already gone)"
                    report_claims.append(entry)
                    continue

            if bid > remaining_budget[team]:
                entry["status"] = "skipped"
                entry["reason"] = (
                    f"insufficient FAAB: bid ${bid} exceeds remaining "
                    f"${remaining_budget[team]}"
                )
                report_claims.append(entry)
                continue

            # Would the resulting roster actually be legal? apply_won_claims
            # raises if a "won" claim turns out to be illegal, and its docstring
            # says resolve_faab's own checks should prevent that — this is the
            # check that was missing. Without it a GM dropping a starter with a
            # full bench got as far as the apply step and took the whole run
            # down with it.
            #
            # The claim is voided rather than charged, which is what the league
            # already does: Ruling 2026-05 refunded a voided bid, and the
            # commissioner's own memos say "no FAAB is charged" for a struck
            # claim.
            probe = copy.deepcopy(working.get(team, rosters.get(team, {})))
            txn = {"type": "add", "player": add_id,
                   "to": claim_target(probe, add_id, players, roster_config, drop_id)}
            if drop_id is not None:
                txn["drop"] = drop_id
            # Only blame a claim for illegality it actually causes. If the
            # roster is already invalid going in, that is not this claim's
            # doing and gating on it would punish the wrong GM.
            was_legal, _ = validate_roster(probe, players, roster_config)
            if was_legal:
                probe["faab_remaining"] = probe.get("faab_remaining", 0) - bid
                try:
                    working[team] = apply_transaction(probe, txn, players,
                                                      roster_config)
                except (ValueError, KeyError) as e:
                    entry["status"] = "skipped"
                    entry["reason"] = f"would leave an illegal roster: {e}"
                    report_claims.append(entry)
                    continue

            # Won and applicable.
            others = [b for t, b in bids_by_add[add_id] if b is not claim]
            if others:
                best_other = max(c["bid"] for c in others)
                entry["reason"] = f"highest bid ${bid} (next best ${best_other})"
            else:
                entry["reason"] = f"uncontested claim, bid ${bid}"
            entry["status"] = "won"
            report_claims.append(entry)

            remaining_budget[team] -= bid
            if drop_id is not None:
                consumed_drops.add(drop_id)

    # A decision that only drops still releases those players. It has no
    # claims to check, and it does not enter the auction.
    for team in drops_by_team:
        if team not in seen_teams:
            _take_standalone_drops(team)

    return {
        "claims": report_claims,
        "drops": report_drops,
        "remaining_budget": remaining_budget,
    }


def claim_target(roster: dict, add_id: str, players: dict, roster_config=None, drop_id=None) -> str:
    """Where a won claim lands (Ruling 2026-10, 2026-10-22): an empty starting
    slot that takes only the added player's position (K, DEF, QB, TE, RB1, ...)
    before the bench; the bench otherwise. A slot the claim's own drop empties
    counts as empty. FLEX-style slots are never filled this way: that is a
    lineup choice, not a roster fact.

    Pure. The first live case: harry-caray's week 7 claim for kicker Cairo
    Santos, with the K slot empty and the bench already over its limit."""
    pos = (players.get(add_id) or {}).get("pos")
    starters = dict(roster.get("starters") or {})
    if drop_id is not None:
        for slot, pid in starters.items():
            if pid == drop_id:
                starters[slot] = None
    for slot, allowed in _starter_slots(roster_config).items():
        if pos and set(allowed) == {pos} and starters.get(slot) is None:
            return slot
    return "bench"


def apply_won_claims(report: dict, rosters: dict, players: dict, roster_config=None, timestamp=None):
    """Apply every 'won' claim in `report` via lib.rosters.apply_transaction.

    Pure: takes rosters (team -> roster dict), returns
    (updated_rosters, transaction_entries) without touching disk. Raises
    ValueError (from apply_transaction) if a 'won' claim is illegal against
    the actual roster state -- resolve_faab's own checks should prevent
    this, but this function does not silently swallow such a failure.
    """
    ts = timestamp or _now_iso()
    updated = {team: copy.deepcopy(roster) for team, roster in rosters.items()}
    entries = []

    # Standalone drops first, per team, so a won claim is applied to the
    # roster resolve_faab already judged legal. Teams with no won claim
    # still release the players they dropped.
    drops_for: dict = {}
    for row in report.get("drops") or []:
        if row.get("status") == "applied" and row.get("team") and row.get("player") is not None:
            drops_for.setdefault(row["team"], []).append(row["player"])
    applied_drop_teams: set = set()

    def _apply_drops(team):
        if team in applied_drop_teams:
            return
        applied_drop_teams.add(team)
        if team not in updated:
            return
        for player_id in drops_for.get(team, []):
            updated[team] = apply_transaction(
                updated[team], {"type": "drop", "player": player_id},
                players, roster_config)
            entries.append({
                "timestamp": ts,
                "team": team,
                "action": "drop",
                "players": [player_id],
                "bid": None,
                "reasoning": "standalone drop",
                "status": "applied",
            })

    for claim in report["claims"]:
        team = claim["team"]
        _apply_drops(team)
        if claim["status"] != "won":
            continue
        txn = {"type": "add", "player": claim["add"],
               "to": claim_target(updated[team], claim["add"], players, roster_config, claim.get("drop"))}
        if claim.get("drop") is not None:
            txn["drop"] = claim["drop"]

        # lib.rosters only knows roster-slot legality, not FAAB -- deduct
        # the winning bid ourselves before handing off to apply_transaction
        # (its own validate_roster call then re-checks faab_remaining >= 0
        # as a second safety net on top of resolve_faab's own budget check).
        current = updated[team]
        current["faab_remaining"] = current.get("faab_remaining", 0) - claim["bid"]

        updated[team] = apply_transaction(current, txn, players, roster_config)
        # Conform to docs/schemas/transaction-entry.json: `action` from the enum,
        # `players` a flat array of ids (add first, then the drop if any),
        # `reasoning` always a string (never null).
        player_ids = [claim["add"]]
        if claim.get("drop") is not None:
            player_ids.append(claim["drop"])
        entries.append({
            "timestamp": ts,
            "team": team,
            "action": "waiver_claim",
            "players": player_ids,
            "bid": claim["bid"],
            "reasoning": claim.get("reasoning") or "",
            "status": "applied",
        })

    for team in drops_for:
        _apply_drops(team)

    return updated, entries


def write_results(updated_rosters: dict, entries: list, rosters_dir: pathlib.Path,
                   transactions_path: pathlib.Path) -> None:
    """Thin disk-writing wrapper: save each changed roster, append transaction
    entries to `transactions_path` (one JSON object per line)."""
    for team, roster in updated_rosters.items():
        save_roster(roster, rosters_dir / team / "roster.json")

    transactions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(transactions_path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


def _load_rosters(rosters_dir: pathlib.Path) -> dict:
    rosters = {}
    for roster_path in sorted(rosters_dir.glob("*/roster.json")):
        team_dir = roster_path.parent.name
        if team_dir.startswith("_"):
            continue
        with open(roster_path, encoding="utf-8") as f:
            rosters[team_dir] = json.load(f)
    return rosters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--claims", required=True, help="path to claims JSON: {team: [claim, ...]}")
    ap.add_argument("--standings", required=True, help="path to standings JSON: [team, ...] worst->best")
    ap.add_argument("--players", default=str(ROOT / "state" / "players.json"))
    ap.add_argument("--rosters-dir", default=str(ROOT / "teams"))
    ap.add_argument("--roster-config", default=None, help="path to config/roster.json (optional)")
    ap.add_argument("--drops", default=None,
                    help="path to standalone drops JSON: {team: [player_id, ...]}")
    ap.add_argument("--report-out", default=None, help="write the resolution report JSON here (default: stdout)")
    ap.add_argument("--transactions", default=str(ROOT / "state" / "transactions.jsonl"))
    ap.add_argument("--dry-run", action="store_true", help="resolve and write the report only; do not apply")
    args = ap.parse_args()

    with open(args.claims, encoding="utf-8") as f:
        claims_by_team = json.load(f)
    drops_by_team = None
    if args.drops:
        with open(args.drops, encoding="utf-8") as f:
            drops_by_team = json.load(f)
    with open(args.standings, encoding="utf-8") as f:
        standings = json.load(f)
    with open(args.players, encoding="utf-8") as f:
        players = json.load(f)

    roster_config = None
    if args.roster_config:
        with open(args.roster_config, encoding="utf-8") as f:
            league_cfg = json.load(f)
        # config/roster.json is {"roster_positions": [...], "settings": {...}}
        # (sync_sleeper.py's shape), not the {"starters": ..., "bench_slots": ...,
        # "ir_slots": ...} shape lib.rosters' validators consume -- adapt it so a
        # synced league's actual slots are honored instead of silently falling
        # through to the hardcoded defaults.
        roster_config = roster_config_from_league(league_cfg)

    rosters_dir = pathlib.Path(args.rosters_dir)
    rosters = _load_rosters(rosters_dir)

    report = resolve_faab(claims_by_team, standings, rosters, players,
                          roster_config, drops_by_team)

    if args.report_out:
        out_path = pathlib.Path(args.report_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"wrote {out_path}")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))

    if not args.dry_run:
        updated_rosters, entries = apply_won_claims(report, rosters, players, roster_config)
        write_results(updated_rosters, entries, rosters_dir, pathlib.Path(args.transactions))
        print(f"applied {len(entries)} won claim(s); appended to {args.transactions}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

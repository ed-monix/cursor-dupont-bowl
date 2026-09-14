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

Resolution report (``resolve_faab`` return value)
--------------------------------------------------

    {"claims": [
        {"team": str, "add": id, "drop": id | None, "bid": int,
         "reasoning": str | None, "status": "won" | "lost" | "skipped",
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
plus the same ``rosters``/``players`` and, for every ``"won"`` claim, calls
``lib.rosters.apply_transaction`` (add with drop, when present) and builds
one ``state/transactions.jsonl`` entry per applied claim::

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
        [--roster-config config/roster.json] \\
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
    apply_transaction, roster_config_from_league, save_roster, validate_roster,
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


def _pick_winner(bids: list[tuple[str, dict]], standings: list[str]) -> tuple[str, dict]:
    """bids: [(team, claim), ...] all bidding on the same add player.
    Highest bid wins; ties broken by worse standing (lower rank index)."""
    def sort_key(item):
        team, claim = item
        return (-claim["bid"], _standing_rank(team, standings))

    ranked = sorted(bids, key=sort_key)
    return ranked[0]


def resolve_faab(claims_by_team: dict, standings: list, rosters: dict,
                 players: dict, roster_config=None) -> dict:
    """Pure FAAB resolution. See module docstring for all shapes. No I/O."""

    # --- Phase 1: bucket every claim by the player it adds, dropping
    # claims for unknown players out of the auction entirely (they can
    # never win) but still recording them as skipped in the report.
    bids_by_add: dict[str, list[tuple[str, dict]]] = {}
    unknown_claims: list[tuple[str, dict]] = []

    for team, claim_list in claims_by_team.items():
        for claim in claim_list:
            add_id = claim["add"]
            if add_id not in players:
                unknown_claims.append((team, claim))
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
    remaining_budget = {
        team: rosters.get(team, {}).get("faab_remaining", 0) for team in claims_by_team
    }

    unknown_lookup = {id(claim): True for _, claim in unknown_claims}

    # A team can win more than one claim, and each changes its roster, so
    # legality has to be checked against the roster as it will actually be
    # when the claim lands — not against the roster it started the run with.
    working: dict = {}

    for team, claim_list in claims_by_team.items():
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
                team_roster = rosters.get(team, {})
                if not _roster_has_player(team_roster, drop_id):
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
            txn = {"type": "add", "player": add_id, "to": "bench"}
            if drop_id is not None:
                txn["drop"] = drop_id
            probe = copy.deepcopy(working.get(team, rosters.get(team, {})))
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

    return {"claims": report_claims, "remaining_budget": remaining_budget}


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

    for claim in report["claims"]:
        if claim["status"] != "won":
            continue
        team = claim["team"]
        txn = {"type": "add", "player": claim["add"], "to": "bench"}
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
    ap.add_argument("--report-out", default=None, help="write the resolution report JSON here (default: stdout)")
    ap.add_argument("--transactions", default=str(ROOT / "state" / "transactions.jsonl"))
    ap.add_argument("--dry-run", action="store_true", help="resolve and write the report only; do not apply")
    args = ap.parse_args()

    with open(args.claims, encoding="utf-8") as f:
        claims_by_team = json.load(f)
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
                          roster_config)

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

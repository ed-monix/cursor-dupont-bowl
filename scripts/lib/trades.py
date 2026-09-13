"""Harness-side trade pre-validation (waivers.md §5, PLAN.md §4 step 5).

GMs may attach an optional `trade_offer` to their weekly decision
(docs/schemas/saturday-decision.json). Week 1 of the live league proved that
nothing checked those offers before dispatching the target agent: two GMs
offered players they did not actually hold, or offers that would have
overflowed the target's roster, and both burned a full extra agent turn on a
trade that was never going to be legal. waivers.md §5 makes the fix a hard
rule: the harness must validate an offer BEFORE spawning the target agent, so
a dead offer costs zero turns instead of one.

This module is that pre-validation gate. It does three things, mirroring
`lib.apply_gate.collect_waiver_claims`'s file-reading pattern and reusing
`lib.rosters.apply_transaction` for the actual legality math rather than
reimplementing roster rules here:

    collect_offers   -- read one offer per team out of decisions/*.json
    validate_offer   -- is a single offer legal right now?
    screen_offers    -- the harness entry point: collect + validate every
                        offer for a week, enforcing the one-offer-per-team
                        and week-11-deadline rules on top

No network. Pure stdlib + the repo's own lib modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from lib.rosters import apply_transaction, roster_config_from_league

TRADE_DEADLINE_WEEK = 11


def collect_offers(decisions_dir: Union[str, Path]) -> dict:
    """{offerer_slug: offer} from gate files named <slug>.json.

    Mirrors `apply_gate.collect_waiver_claims`: only plain `<slug>.json`
    decision files are considered (never `<slug>.lineup-*.json` or
    `<slug>.trade.json`, which are lineup submissions and trade *responses*
    respectively, not offers). A decision file is only included if it
    actually carries a non-empty `trade_offer` object -- most weeks, most
    teams offer nothing. Unreadable or malformed files are skipped, same as
    collect_waiver_claims tolerates them (a bad file must not crash the
    whole run).
    """
    decisions_dir = Path(decisions_dir)
    out: dict = {}
    if not decisions_dir.is_dir():
        return out
    for path in sorted(decisions_dir.glob("*.json")):
        name = path.name
        if ".lineup-" in name or name.endswith(".trade.json"):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        offer = obj.get("trade_offer")
        if isinstance(offer, dict) and offer:
            out[path.stem] = offer
    return out


def validate_offer(
    offerer: str,
    offer: dict,
    rosters: dict,
    players: dict,
    roster_config: Optional[dict] = None,
) -> tuple[bool, str]:
    """Is `offer` (from `offerer`) legal right now? Returns (ok, reason).

    `reason` is a short human-readable string, empty when ok is True. Checks
    run cheapest/most-obvious first so the reason a bad offer gets rejected
    for is the most useful one to show a GM:

        1. to_team names a real, different team
        2. out/in are both non-empty lists of player ids
        3. the offerer actually holds every `out` id
        4. the target actually holds every `in` id
        5. the swap leaves BOTH rosters valid (via rosters.apply_transaction,
           which already knows bench/ir limits, duplicate players, etc. --
           never reimplemented here)
    """
    to_team = offer.get("to_team")
    if not to_team or to_team not in rosters:
        return False, f"unknown to_team {to_team!r}"
    if to_team == offerer:
        return False, "cannot trade with yourself"

    out_ids = offer.get("out")
    in_ids = offer.get("in")
    if not isinstance(out_ids, list) or not out_ids:
        return False, "offer 'out' must be a non-empty list of player ids"
    if not isinstance(in_ids, list) or not in_ids:
        return False, "offer 'in' must be a non-empty list of player ids"

    offerer_roster = rosters.get(offerer)
    if offerer_roster is None:
        return False, f"unknown offerer {offerer!r}"
    target_roster = rosters[to_team]

    offerer_ids = _all_player_ids(offerer_roster)
    missing_out = [pid for pid in out_ids if pid not in offerer_ids]
    if missing_out:
        return False, f"{offerer} does not hold: {', '.join(missing_out)}"

    target_ids = _all_player_ids(target_roster)
    missing_in = [pid for pid in in_ids if pid not in target_ids]
    if missing_in:
        return False, f"{to_team} does not hold: {', '.join(missing_in)}"

    try:
        apply_transaction(
            offerer_roster, {"type": "trade", "out": out_ids, "in": in_ids},
            players, roster_config,
        )
    except ValueError as exc:
        return False, f"{offerer}'s side: {exc}"

    try:
        apply_transaction(
            target_roster, {"type": "trade", "out": in_ids, "in": out_ids},
            players, roster_config,
        )
    except ValueError as exc:
        return False, f"{to_team}'s side: {exc}"

    return True, ""


def screen_offers(
    root: Union[str, Path],
    season: str,
    week: int,
    *,
    rosters: Optional[dict] = None,
    players: Optional[dict] = None,
    roster_config: Optional[dict] = None,
) -> list:
    """The harness gate: collect every offer for `season`/`week` and
    validate each one before anything is dispatched to a target agent.

    Returns a list of records, one per offering team::

        {"from": slug, "offer": {...}, "ok": bool, "reason": str}

    On top of `validate_offer`'s per-offer checks, this enforces the two
    rules waivers.md §5 calls out by name:

    - max one outgoing offer per team per week. The schema already only
      allows one `trade_offer` per decision file, so a second offer from
      the same team can only happen if something upstream misbehaves --
      this is the belt-and-braces check for that.
    - the week-11 trade deadline ("deadline end of week 11": week 11 offers
      are still allowed, week 12 and beyond are not).

    `rosters`/`players`/`roster_config` may be passed in directly (tests do
    this); when omitted they are loaded the way scripts/faab.py loads them:
    `teams/*/roster.json` (skipping `_template` and other underscore dirs),
    `state/players.json`, and -- if `config/roster.json` exists -- adapted
    with `roster_config_from_league` into the shape `apply_transaction`
    expects.
    """
    root = Path(root)
    if rosters is None:
        rosters = _load_rosters(root / "teams")
    if players is None:
        players = _load_players(root / "state" / "players.json")
    if roster_config is None:
        roster_config = _load_roster_config(root / "config" / "roster.json")

    decisions_dir = root / "state" / "weeks" / f"{season}-w{week:02d}" / "decisions"
    offers = collect_offers(decisions_dir)

    # Belt-and-braces: the schema caps a decision at one trade_offer, so this
    # can only ever fire if collect_offers is fed more than one decision file
    # per team, or upstream produces a duplicate -- still assert it.
    seen: set = set()
    records = []
    for slug, offer in offers.items():
        if slug in seen:
            records.append({
                "from": slug, "offer": offer, "ok": False,
                "reason": f"{slug} already has an outgoing offer this week",
            })
            continue
        seen.add(slug)

        if week > TRADE_DEADLINE_WEEK:
            records.append({
                "from": slug, "offer": offer, "ok": False,
                "reason": f"trade deadline was end of week {TRADE_DEADLINE_WEEK}",
            })
            continue

        ok, reason = validate_offer(slug, offer, rosters, players, roster_config)
        records.append({"from": slug, "offer": offer, "ok": ok, "reason": reason})

    return records


def _all_player_ids(roster: dict) -> set:
    ids = set()
    for pid in (roster.get("starters") or {}).values():
        if pid is not None:
            ids.add(pid)
    ids.update(roster.get("bench") or [])
    ids.update(roster.get("ir") or [])
    return ids


def _load_rosters(rosters_dir: Path) -> dict:
    rosters = {}
    for roster_path in sorted(rosters_dir.glob("*/roster.json")):
        team_dir = roster_path.parent.name
        if team_dir.startswith("_"):
            continue
        rosters[team_dir] = json.loads(roster_path.read_text(encoding="utf-8"))
    return rosters


def _load_players(players_path: Path) -> dict:
    if not players_path.exists():
        return {}
    return json.loads(players_path.read_text(encoding="utf-8"))


def _load_roster_config(config_path: Path) -> Optional[dict]:
    if not config_path.exists():
        return None
    league_cfg = json.loads(config_path.read_text(encoding="utf-8"))
    return roster_config_from_league(league_cfg)

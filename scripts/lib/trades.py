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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from lib.rosters import (apply_transaction,
                         roster_config_from_league, save_roster)

TRADE_DEADLINE_WEEK = 11


MAX_OFFERS_PER_TEAM = 3


def collect_offers(decisions_dir: Union[str, Path]) -> dict:
    """{offerer_slug: [offer, ...]} from gate files named <slug>.json.

    Mirrors `apply_gate.collect_waiver_claims`: only plain `<slug>.json`
    decision files are considered (never `<slug>.lineup-*.json` or
    `<slug>.trade.json`, which are lineup submissions and trade *responses*
    respectively, not offers). Unreadable or malformed files are skipped, same
    as collect_waiver_claims tolerates them (a bad file must not crash the
    whole run).

    A team may make up to MAX_OFFERS_PER_TEAM offers a week. It used to be one,
    which made the trade market almost inert: a GM got a single shot, and if the
    target said no -- both of week 2's did -- that was the whole market for the
    week. `trade_offers` is the list form; `trade_offer` is still read as a
    single offer so older decision files and any GM that writes the old key
    keep working.
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

        offers = []
        many = obj.get("trade_offers")
        if isinstance(many, list):
            offers.extend(o for o in many if isinstance(o, dict) and o)
        one = obj.get("trade_offer")
        if isinstance(one, dict) and one:
            offers.append(one)
        if offers:
            out[path.stem] = offers
    return out


def _active_ids(roster: dict) -> list:
    """Starters + bench. IR is not a trading or dropping pool."""
    ids = [str(pid) for pid in (roster.get("starters") or {}).values() if pid]
    ids += [str(pid) for pid in (roster.get("bench") or [])]
    return ids


def droppable_for(roster: dict, gone: list, got: list) -> list:
    """Players this side could cut to make room for `got`, bench first.

    Not the ones leaving in the trade (already going) and not the ones arriving
    (accepting a player to immediately waive him is not a trade, it is a
    laundering of somebody else's roster crunch). Bench first because incoming
    players land on the bench, so a bench cut is what actually relieves the
    pressure -- dropping a starter empties a lineup slot and helps nothing.
    """
    busy = {str(p) for p in gone} | {str(p) for p in got}
    bench = [str(p) for p in (roster.get("bench") or []) if str(p) not in busy]
    starters = [str(p) for p in (roster.get("starters") or {}).values()
                if p and str(p) not in busy]
    return bench + starters


def drops_needed(roster: dict, gone: list, got: list, players: dict,
                 roster_config: Optional[dict] = None) -> Optional[int]:
    """Fewest players this side must cut for the swap to be legal. Usually 0.

    Asked, not calculated. An earlier version of this did the capacity
    arithmetic by hand and got it wrong: it compared total roster size against
    total slots, when `apply_transaction` puts every incoming player on the
    *bench*. Trading away a starter empties a lineup slot and relieves no bench
    pressure at all, so a 2-for-1 for somebody's starter still overflowed and
    the screen still said no. Rather than model the rules a second time and be
    wrong a second time, this drops one more player at a time and asks
    apply_transaction -- the only thing that actually knows -- whether it fits
    yet.

    Returns None if no number of drops makes it legal, which means the offer is
    broken for a reason that is not roster space.
    """
    can = droppable_for(roster, gone, got)
    for n in range(0, len(can) + 1):
        candidate = roster
        try:
            for pid in can[:n]:
                candidate = apply_transaction(
                    candidate, {"type": "drop", "player": pid},
                    players, roster_config)
            apply_transaction(
                candidate, {"type": "trade", "out": gone, "in": got},
                players, roster_config)
            return n
        except ValueError:
            continue
    return None


def validate_offer(
    offerer: str,
    offer: dict,
    rosters: dict,
    players: dict,
    roster_config: Optional[dict] = None,
) -> tuple[bool, str]:
    """Is `offer` (from `offerer`) legal right now?

    Returns `(ok, reason, requires_drop)`. `requires_drop` is `{team: n}` when a
    side must cut `n` players to fit the swap, else None -- an uneven trade is
    legal, it just costs the receiving side roster space.

    `reason` is a short human-readable string, empty when ok is True. Checks
    run cheapest/most-obvious first so the reason a bad offer gets rejected
    for is the most useful one to show a GM:

        1. to_team names a real, different team
        2. out/in are both non-empty lists of player ids
        3. the offerer actually holds every `out` id
        4. the target actually holds every `in` id
        5. the swap leaves BOTH rosters valid (via rosters.apply_transaction,
           which already knows bench/ir limits, duplicate players, etc. --
           never reimplemented here), allowing for the drops each side would
           have to make: a side over the limit is asked for room, not refused
    """
    to_team = offer.get("to_team")
    if not to_team or to_team not in rosters:
        return False, f"unknown to_team {to_team!r}", None
    if to_team == offerer:
        return False, "cannot trade with yourself", None

    out_ids = offer.get("out")
    in_ids = offer.get("in")
    if not isinstance(out_ids, list) or not out_ids:
        return False, "offer 'out' must be a non-empty list of player ids", None
    if not isinstance(in_ids, list) or not in_ids:
        return False, "offer 'in' must be a non-empty list of player ids", None

    offerer_roster = rosters.get(offerer)
    if offerer_roster is None:
        return False, f"unknown offerer {offerer!r}", None
    target_roster = rosters[to_team]

    offerer_ids = _all_player_ids(offerer_roster)
    missing_out = [pid for pid in out_ids if pid not in offerer_ids]
    if missing_out:
        return False, f"{offerer} does not hold: {', '.join(missing_out)}", None

    target_ids = _all_player_ids(target_roster)
    missing_in = [pid for pid in in_ids if pid not in target_ids]
    if missing_in:
        return False, f"{to_team} does not hold: {', '.join(missing_in)}", None

    requires_drop = {}
    for team, roster, gone, got, named, must_name in (
        (offerer, offerer_roster, out_ids, in_ids, offer.get("drop"), True),
        (to_team, target_roster, in_ids, out_ids, None, False),
    ):
        need = drops_needed(roster, gone, got, players, roster_config)
        if need is None:
            # No number of cuts fixes it, so the problem is not roster space.
            # Re-run the bare swap to surface the real reason.
            try:
                apply_transaction(
                    roster, {"type": "trade", "out": gone, "in": got},
                    players, roster_config)
            except ValueError as exc:
                return False, f"{team}'s side: {exc}", None
            return False, f"{team}'s side: cannot be made legal", None

        # The offerer names its own drops up front -- it knew it was taking
        # back more than it sent, so who it cuts is part of the offer. The
        # target has not been asked yet and names them when it accepts, so for
        # that side drops_needed has already proven a legal set of that size
        # exists and the real names arrive with the acceptance.
        if must_name and need:
            chosen = [str(x) for x in (named or [])]
            if len(chosen) < need:
                return False, (f"{team}'s side: offer takes back {need} more "
                               f"than it sends and names only {len(chosen)} "
                               f"drop(s)"), None
            candidate = roster
            try:
                for pid in chosen[:need]:
                    candidate = apply_transaction(
                        candidate, {"type": "drop", "player": pid},
                        players, roster_config)
                apply_transaction(
                    candidate, {"type": "trade", "out": gone, "in": got},
                    players, roster_config)
            except ValueError as exc:
                return False, f"{team}'s side: named drops do not work: {exc}", None

        if need:
            requires_drop[team] = need

    return True, "", requires_drop if requires_drop else None


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

    records = []
    for slug, team_offers in offers.items():
        for index, offer in enumerate(team_offers):
            # Offers past the cap are refused in submission order, so a GM that
            # writes four keeps its first three rather than losing all of them.
            if index >= MAX_OFFERS_PER_TEAM:
                records.append({
                    "from": slug, "offer": offer, "ok": False,
                    "reason": (f"{slug} may make at most {MAX_OFFERS_PER_TEAM} "
                               f"offers a week; this was number {index + 1}"),
                })
                continue

            if week > TRADE_DEADLINE_WEEK:
                records.append({
                    "from": slug, "offer": offer, "ok": False,
                    "reason": f"trade deadline was end of week {TRADE_DEADLINE_WEEK}",
                })
                continue

            ok, reason, requires_drop = validate_offer(
                slug, offer, rosters, players, roster_config)
            rec = {"from": slug, "offer": offer, "ok": ok, "reason": reason}
            if requires_drop:
                # The target reads this in its pack: accepting costs it this
                # many roster spots, and it names the casualties in its reply.
                rec["requires_drop"] = requires_drop
            records.append(rec)

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


def collect_responses(decisions_dir: Union[str, Path]) -> dict:
    """{target_slug: {offerer_slug: response}} from `<slug>.trade.json` files.

    A target can now be sent up to three offers by three different teams in the
    same week, and it answers all of them in one turn, so a response file holds
    a `responses` list whose entries name the offer they answer via `from`. A
    file in the older flat shape (a bare `response` at the top level) is still
    read; with only one offer in front of it there is no ambiguity, so it is
    filed under None and matched to whatever offer that target received.
    """
    out: dict = {}
    decisions_dir = Path(decisions_dir)
    if not decisions_dir.is_dir():
        return out
    for path in sorted(decisions_dir.glob("*.trade.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        target = path.name[: -len(".trade.json")]

        answers: dict = {}
        many = obj.get("responses")
        if isinstance(many, list):
            for item in many:
                if isinstance(item, dict) and item.get("response"):
                    answers[item.get("from")] = item
        if obj.get("response"):
            answers.setdefault(None, obj)
        if answers:
            out[target] = answers
    return out


def _apply_one(cand, state, rosters, players, roster_config, stamp):
    """Apply one accepted offer onto `state`. Returns (new_state, entries).

    Raises ValueError if it does not fit, so callers can use this both to
    really apply a trade and to ask whether a set of trades can coexist.
    """
    offerer, target = cand["from"], cand["target"]
    offer, response = cand["offer"], cand["response"]
    out_ids = list(offer.get("out") or [])
    in_ids = list(offer.get("in") or [])
    needed = cand.get("requires_drop") or {}
    drops = {offerer: [str(x) for x in (offer.get("drop") or [])],
             target: [str(x) for x in (response.get("drop") or [])]}

    state = dict(state)
    entries = []
    for team in (offerer, target):
        for pid in (drops.get(team) or [])[:needed.get(team, 0)]:
            state[team] = apply_transaction(
                state.get(team, rosters[team]),
                {"type": "drop", "player": pid}, players, roster_config)
            entries.append({
                "timestamp": stamp, "team": team, "action": "drop",
                "players": [pid], "bid": None,
                "reasoning": "dropped to make room for an accepted trade",
                "status": "applied",
            })
    state[offerer] = apply_transaction(
        state.get(offerer, rosters[offerer]),
        {"type": "trade", "out": out_ids, "in": in_ids}, players, roster_config)
    state[target] = apply_transaction(
        state.get(target, rosters[target]),
        {"type": "trade", "out": in_ids, "in": out_ids}, players, roster_config)

    reasoning = (response.get("message") or offer.get("message") or "").strip()
    for team, gone, got in ((offerer, out_ids, in_ids), (target, in_ids, out_ids)):
        entries.append({
            "timestamp": stamp, "team": team, "action": "trade",
            "players": list(gone) + list(got), "bid": None,
            "reasoning": reasoning, "status": "applied",
        })
    return state, entries


def offers_coexist(cands, state, rosters, players, roster_config) -> bool:
    """Can all of one team's accepted offers be honoured together?

    Usually yes: a GM who sent three offers for three different players and got
    three yeses has simply had a good week. It is only when the accepts overlap
    -- the same player promised twice, or a combination the roster cannot carry
    -- that somebody has to choose.
    """
    try:
        for cand in cands:
            state, _ = _apply_one(cand, state, rosters, players, roster_config,
                                  "1970-01-01T00:00:00+00:00")
    except (ValueError, KeyError):
        return False
    return True


def apply_accepted(root: Union[str, Path], season: str, week: int, *,
                   dry_run: bool = False, choose=None) -> list:
    """Execute every accepted offer and log it. Returns one record per response.

    Until this existed, a GM could accept a trade and nothing happened: the
    response sat in `<slug>.trade.json`, `collect_waiver_claims` skipped it by
    name, and no roster ever changed. waivers.md §6 says "apply approved trades
    the same way" -- by hand, in the human flow. There is no hand in the office.

    A team may now send up to three offers, so several of its offers can come
    back accepted at once. If they all fit together they are all honoured. If
    they cannot -- the same player promised to two teams, or a combination the
    roster will not carry -- the OFFERING GM chooses which to honour, via
    `choose(offerer, candidates) -> [chosen]`. That choice is a football
    decision and belongs to the GM; the harness applying the first and voiding
    the rest by screening order would be the harness deciding a trade. Without
    a chooser (tests, dry runs) the first that fits wins and the rest are
    reported, never silently dropped.

    `counter` is recorded, never auto-applied. A counter is a fresh offer back
    to the original offerer, and chasing it automatically is an unbounded
    negotiation; it goes to the commissioner and the next run instead.

    The swap itself is lib.rosters.apply_transaction on both sides, so trades
    obey exactly the same roster rules as every other transaction.
    """
    root = Path(root)
    wdir = root / "state" / "weeks" / f"{season}-w{week:02d}"
    try:
        screen = json.loads((wdir / "trade-screen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        screen = []

    by_target: dict = {}
    for r in screen:
        if isinstance(r, dict) and r.get("ok") and r.get("offer"):
            by_target.setdefault(r["offer"].get("to_team"), []).append(r)
    responses = collect_responses(wdir / "decisions")

    rosters = _load_rosters(root / "teams")
    players = _load_players(root / "state" / "players.json")
    roster_config = _load_roster_config(root / "config" / "roster.json")

    results, entries, state = [], [], {}
    stamp = datetime.now(timezone.utc).isoformat()

    # ---- match each answer to the offer it answers -----------------------
    accepted: dict = {}
    for target, answers in sorted(responses.items()):
        screened_for_target = by_target.get(target) or []
        if not screened_for_target:
            for answer in answers.values():
                results.append({"target": target,
                                "response": answer.get("response"),
                                "applied": False,
                                "reason": "no screened offer for this target"})
            continue

        for screened in screened_for_target:
            offerer = screened["from"]
            # `from` names the offer when several arrived; a lone offer may
            # still be answered in the older flat shape, filed under None.
            answer = answers.get(offerer)
            if answer is None and len(screened_for_target) == 1:
                answer = answers.get(None)
            if answer is None:
                results.append({"target": target, "from": offerer,
                                "applied": False,
                                "reason": "no response to this offer"})
                continue

            rec = {"target": target, "from": offerer,
                   "response": answer.get("response")}
            if answer.get("response") != "accept":
                rec.update(applied=False,
                           reason=f"{answer.get('response')} — nothing to apply")
                results.append(rec)
                continue

            needed = screened.get("requires_drop") or {}
            drops = {offerer: [str(x) for x in (screened["offer"].get("drop") or [])],
                     target: [str(x) for x in (answer.get("drop") or [])]}
            short = {team: n for team, n in needed.items()
                     if len(drops.get(team) or []) < n}
            if short:
                rec.update(applied=False, reason="; ".join(
                    f"{team} must drop {n} to fit this trade and named "
                    f"{len(drops.get(team) or [])}"
                    for team, n in sorted(short.items())))
                results.append(rec)
                continue

            accepted.setdefault(offerer, []).append({
                "from": offerer, "target": target, "offer": screened["offer"],
                "response": answer, "requires_drop": needed,
            })

    # ---- an offerer with several accepts may have to choose --------------
    for offerer in sorted(accepted):
        cands = accepted[offerer]
        if len(cands) > 1 and not offers_coexist(cands, state, rosters, players,
                                                 roster_config):
            chosen = None
            if choose is not None:
                chosen = choose(offerer, cands)
            if chosen is None:
                # No chooser: keep what fits, in order, and say so.
                chosen = []
                probe = dict(state)
                for cand in cands:
                    try:
                        probe, _ = _apply_one(cand, probe, rosters, players,
                                              roster_config, stamp)
                        chosen.append(cand)
                    except (ValueError, KeyError):
                        pass
            keep = {id(c) for c in chosen}
            for cand in cands:
                if id(cand) not in keep:
                    results.append({
                        "target": cand["target"], "from": offerer,
                        "response": "accept", "applied": False,
                        "reason": ("accepted, but conflicts with another offer "
                                   f"{offerer} chose to honour instead"),
                    })
            cands = chosen

        for cand in cands:
            rec = {"target": cand["target"], "from": offerer, "response": "accept"}
            try:
                state, new_entries = _apply_one(cand, state, rosters, players,
                                                roster_config, stamp)
            except (ValueError, KeyError) as e:
                # The screen passed it, but rosters move during a run (FAAB
                # applies first). No longer legal is reported, not forced.
                rec.update(applied=False, reason=f"illegal at apply time: {e}")
                results.append(rec)
                continue
            entries.extend(new_entries)
            rec.update(applied=True, reason="")
            results.append(rec)

    if not dry_run and state:
        for team, roster in state.items():
            save_roster(roster, root / "teams" / team / "roster.json")
        tx = root / "state" / "transactions.jsonl"
        tx.parent.mkdir(parents=True, exist_ok=True)
        with open(tx, "a", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, sort_keys=True) + "\n")

    return results

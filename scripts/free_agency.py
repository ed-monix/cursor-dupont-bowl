#!/usr/bin/env python3
"""free_agency.py — post-waiver free agency for one team, on game day.

Once waivers clear, a free agent can be signed outright: no FAAB, first come,
first served. This is that window. It is NOT an owner move (CLAUDE.md rule 7):
the team's own GM gets an isolated turn, sees his roster and the free agents
whose games have not started, and decides. Scripts decide everything else —
who is actually a free agent (from the rosters, never a cached list), whether
a game has kicked, and whether the result is legal.

    python scripts/free_agency.py --team your-team --week 5 --pos QB \\
        --context "Owner reports: Caleb is out today."

Commissioner review (CLAUDE.md rule 6): after the GM decides and the scripts
have built and validated the result, the commissioner reviews the exact move —
on Opus, isolated, the same persona as every other gate — and returns a verdict.
Nothing is written to a roster until it says approve. A block, or a review that
fails to run at all, applies nothing: this fails closed, because a move the
office could not review is a move it did not approve.

Every attempt — stand pat, refused, blocked, applied — is appended to
decisions/<slug>.free-agency.json. Rosters, lineups.json and transactions.jsonl
change only on approval. Does not commit.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_week  # noqa: E402
from lib import claude_turn, nfl_slate  # noqa: E402
import agent_turn  # noqa: E402
from lib.apply_lineups import reconciled_bench  # noqa: E402
from lib.rosters import (apply_transaction, injury_bars_starting,  # noqa: E402
                         validate_lineup, validate_roster)
from lib.scoring import score_player  # noqa: E402

SCHEMA = {
    "type": "object",
    "required": ["add", "drop", "start_slot", "reasoning"],
    "properties": {
        "add": {"type": ["string", "null"], "description": "free agent id, or null to stand pat"},
        "drop": {"type": ["string", "null"], "description": "your player id to release, required if you add"},
        "start_slot": {"type": ["string", "null"], "description": "slot to start the new man in, e.g. QB, or null to bench him"},
        "reasoning": {"type": "string", "description": "in your own voice, for the permanent record"},
    },
    "additionalProperties": False,
}


def _j(p, d=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def rostered_ids(root):
    ids = set()
    for f in (root / "teams").glob("*/roster.json"):
        if f.parent.name.startswith("_"):
            continue
        r = _j(f, {})
        ids |= {str(v) for v in (r.get("starters") or {}).values() if v}
        ids |= {str(v) for v in (r.get("bench") or []) + (r.get("ir") or [])}
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--pos", default=None, help="limit candidates to one position")
    ap.add_argument("--context", default="", help="what prompted the window, shown to the GM")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--reviewer-model", default=agent_turn.DEFAULT_MODEL,
                    help="the commissioner's model (Opus, like every other gate)")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root)
    wdir = root / "state" / "weeks" / f"{a.season}-w{a.week:02d}"

    players = _j(root / "state" / "players.json", {})
    config = _j(root / "config" / "roster.json", {})
    proj = _j(wdir / "projections.json", {}) or {}
    scoring = score_week.load_scoring(root / "config")
    games = nfl_slate.index_games_by_team(_j(wdir / "nfl-games.json", []))
    rpath = root / "teams" / a.team / "roster.json"
    roster = _j(rpath)
    gm_md = (root / "teams" / a.team / "general-manager.md").read_text(encoding="utf-8")

    def kicked(pid):
        p = players.get(str(pid), {})
        return nfl_slate.game_has_kicked(nfl_slate.lookup_game(p.get("team"), games))

    def card(pid):
        p = players.get(str(pid), {})
        g = nfl_slate.lookup_game(p.get("team"), games) or {}
        return {"id": str(pid), "name": p.get("name"), "pos": p.get("pos"),
                "nfl": p.get("team"), "injury": p.get("injury"),
                "proj_pts": round(score_player(proj.get(str(pid), {}) or {}, scoring), 2),
                "game": f"{g.get('away')} @ {g.get('home')}" if g else "bye",
                "kicked": kicked(pid)}

    taken = rostered_ids(root)
    cands = []
    for pid, p in players.items():
        if pid in taken or (a.pos and p.get("pos") != a.pos):
            continue
        if injury_bars_starting(p) or p.get("injury"):
            continue
        if not nfl_slate.lookup_game(p.get("team"), games) or kicked(pid):
            continue
        cands.append(card(pid))
    cands.sort(key=lambda c: -c["proj_pts"])
    cands = cands[: a.limit]

    pack = {
        "situation": a.context,
        "your_starters": {s: card(v) for s, v in roster["starters"].items() if s != "DEF"},
        "your_bench": [card(v) for v in roster["bench"]],
        "free_agents": cands,
        "rules": [
            "Free agency: waivers have cleared, so a free agent is signed outright. No FAAB is spent.",
            "Sign at most one. Your roster is full, so you must also release one player (not one whose game has kicked).",
            "You may start the new man today only if neither his game nor the game of the man he replaces has kicked off.",
            "You may also stand pat: add null.",
            "Nothing here is an order. Your GM file decides.",
        ],
    }
    system = (gm_md + "\n\n## House rules\nDo NOT read files, run commands or use tools. "
              "Everything you need is in the JSON below. Decide in character, then reply "
              "with ONE JSON object matching the schema.")
    print(f"free agency: {a.team}, {len(cands)} candidate(s)")
    res = claude_turn.run_turn(system_text=system, user_text=json.dumps(pack, indent=1),
                               model=a.model, schema=SCHEMA, label=f"{a.team}-fa")
    dec = json.loads(res.text)
    print("decision:", json.dumps(dec)[:600])
    log = DecisionLog(wdir / "decisions" / f"{a.team}.free-agency.json", dec)

    if not dec.get("add"):
        log.write("stood_pat")
        print("stood pat — nothing to apply")
        return 0

    add, drop, slot = str(dec["add"]), str(dec.get("drop") or ""), dec.get("start_slot")
    if add not in {c["id"] for c in cands}:
        return log.refuse(f"{add} was not one of the offered free agents")
    if not drop or kicked(drop):
        return log.refuse("a drop is required, and not a player whose game has kicked")

    try:
        new = apply_transaction(roster, {"type": "drop", "player": drop}, players, config)
        new = apply_transaction(new, {"type": "add", "player": add, "to": "bench"},
                                players, config)
    except ValueError as e:
        return log.refuse(f"illegal: {e}")

    lineups = _j(wdir / "lineups.json", {}) or {}
    side = copy.deepcopy(lineups.get(a.team) or {})
    if slot:
        old = new["starters"].get(slot)
        if old and kicked(old):
            return log.refuse(f"{slot} holds a player whose game has kicked")
        starters = dict(new["starters"]); starters[slot] = add
        new["bench"] = reconciled_bench(new, starters)
        new["starters"] = starters
        if side:
            side.setdefault("starters", {})[slot] = add
            g = nfl_slate.lookup_game(players[add].get("team"), games) or {}
            side.setdefault("locked_slots", {})[slot] = {
                "player_id": add, "nfl": players[add].get("team"),
                "game_date": g.get("date"), "kicked": False, "window": "main",
                "free_agency": True}
    ok, err = validate_roster(new, players, config)
    ok2, err2 = validate_lineup(new, players, config)
    if not (ok and ok2):
        return log.refuse(f"result is illegal: {err} {err2}")

    # ---- the commissioner reviews the exact move, before anything is written
    review_pack = {
        "team": a.team, "week": a.week, "season": a.season,
        "situation": a.context,
        "decision": dec,
        "offered_free_agents": cands,
        "players_involved": {pid: card(pid) for pid in filter(None, [
            add, drop, roster["starters"].get(slot) if slot else None])},
        "roster_before": roster, "roster_after": new,
        "scripted_checks": "passed: offered player, drop not kicked, slot not "
                           "kicked, legal roster, legal lineup",
        "general_manager_file": gm_md,
        "rulings": (root / "state" / "rulings.md").read_text(encoding="utf-8")
                   if (root / "state" / "rulings.md").exists() else "",
    }
    try:
        verdict = review(root, review_pack, a.reviewer_model)
    except (claude_turn.TurnError, ValueError) as e:
        log.review = {"verdict": "unavailable", "error": str(e)}
        log.write("review_failed")
        print(f"NOT APPLIED: commissioner review did not run ({e}) — fails closed")
        return 3
    log.review = verdict
    print(f"commissioner: {verdict['verdict']}"
          + (f" — {verdict.get('rule')}" if verdict.get("rule") else ""))

    stamp = datetime.now(timezone.utc).isoformat()
    entry = {"timestamp": stamp, "team": a.team, "action": "free_agent",
             "players": [add, drop], "bid": 0, "reasoning": dec["reasoning"]}
    if verdict["verdict"] != "approve":
        log.write("blocked")
        _append_tx(root, dict(entry, status="rejected"))
        print("NOT APPLIED: blocked by the commissioner")
        return 4

    (root / "teams" / a.team / "roster.json").write_text(
        json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if side:
        lineups[a.team] = side
        (wdir / "lineups.json").write_text(json.dumps(lineups, indent=2) + "\n",
                                          encoding="utf-8")
    _append_tx(root, dict(entry, status="applied"))
    log.write("applied")
    print(f"applied: +{players[add]['name']} -{players.get(drop, {}).get('name')}"
          + (f", starting at {slot}" if slot else ", to the bench"))
    return 0


REVIEW_SCHEMA = {
    "type": "object",
    "required": ["verdict", "rule", "signoff"],
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "block"]},
        "rule": {"type": ["string", "null"],
                 "description": "the rule broken, when blocking; else null"},
        "signoff": {"type": "string", "description": "your signoff, in your voice"},
    },
    "additionalProperties": False,
}

REVIEW_CONTRACT = """
## Your output

A single free-agency signing, made between waiver runs, is in front of you
before anything is applied. Return ONE JSON object: `verdict` approve or block,
`rule` naming the specific rule broken when you block (null otherwise), and a
short `signoff` in your own voice.

Block only a rule violation: a player who was not genuinely a free agent, a
move touching a player or slot whose game has kicked, an illegal roster or
lineup, collusion, or anything that contradicts a standing ruling. A signing
you think is stupid is legal — say so in the signoff and approve it. Approving
is the normal outcome.
"""


def review(root, pack, model):
    """The commissioner's verdict on one move. Raises if it cannot be had."""
    system = "\n".join([
        agent_turn.persona(root, "commissioner"), "", "---", "",
        "You are running as a one-shot turn. You have no tools and no file "
        "system. Everything you are permitted to know is in the JSON below.",
        REVIEW_CONTRACT,
    ])
    res = claude_turn.run_turn(system_text=system,
                               user_text=json.dumps(pack, indent=1),
                               model=model, schema=REVIEW_SCHEMA,
                               label=f"{pack['team']}-fa-review")
    verdict = json.loads(res.text)
    if verdict.get("verdict") not in ("approve", "block"):
        raise ValueError(f"unusable verdict: {verdict!r}")
    return verdict


class DecisionLog:
    """Appends every free-agency attempt for a team-week, whatever its outcome.

    A team may use the window more than once in a week, so the file is a list.
    An older single-object file (the first use, before review existed) is kept
    as the first entry rather than overwritten.
    """

    def __init__(self, path, decision):
        self.path, self.decision, self.review = path, decision, None

    def write(self, outcome, reason=None):
        existing = _j(self.path, [])
        if isinstance(existing, dict):
            existing = [existing]
        existing.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": self.decision, "outcome": outcome,
            **({"reason": reason} if reason else {}),
            **({"review": self.review} if self.review else {}),
        })
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    def refuse(self, reason):
        self.write("refused", reason)
        print(f"REFUSED: {reason}")
        return 2


def _append_tx(root, entry):
    with open(root / "state" / "transactions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

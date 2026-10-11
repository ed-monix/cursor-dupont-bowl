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

Writes decisions/<slug>.free-agency.json, the roster, lineups.json and
transactions.jsonl. Does not commit.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_week  # noqa: E402
from lib import claude_turn, nfl_slate  # noqa: E402
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
    (wdir / "decisions").mkdir(parents=True, exist_ok=True)
    (wdir / "decisions" / f"{a.team}.free-agency.json").write_text(
        json.dumps(dec, indent=2) + "\n", encoding="utf-8")
    print("decision:", json.dumps(dec)[:600])

    if not dec.get("add"):
        print("stood pat — nothing to apply")
        return 0

    add, drop, slot = str(dec["add"]), str(dec.get("drop") or ""), dec.get("start_slot")
    if add not in {c["id"] for c in cands}:
        print(f"REFUSED: {add} was not one of the offered free agents"); return 2
    if not drop or kicked(drop):
        print("REFUSED: a drop is required, and not a player whose game has kicked"); return 2

    new = apply_transaction(roster, {"type": "drop", "player": drop}, players, config)
    new = apply_transaction(new, {"type": "add", "player": add, "to": "bench"}, players, config)

    lpath = wdir / "lineups.json"
    lineups = _j(lpath, {}) or {}
    side = copy.deepcopy(lineups.get(a.team) or {})
    if slot:
        old = new["starters"].get(slot)
        if old and kicked(old):
            print(f"REFUSED: {slot} holds a player whose game has kicked"); return 2
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
    if side.get("starters", {}).get(slot) is None and slot:
        pass
    ok, err = validate_roster(new, players, config)
    ok2, err2 = validate_lineup(new, players, config)
    if not (ok and ok2):
        print("REFUSED: result is illegal:", err, err2); return 2

    rpath.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if side:
        lineups[a.team] = side
        lpath.write_text(json.dumps(lineups, indent=2) + "\n", encoding="utf-8")
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).isoformat()
    with open(root / "state" / "transactions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": stamp, "team": a.team, "action": "free_agent",
                            "players": [add, drop], "bid": 0, "reasoning": dec["reasoning"],
                            "status": "applied"}, sort_keys=True) + "\n")
    print(f"applied: +{players[add]['name']} -{players.get(drop, {}).get('name')}"
          + (f", starting at {slot}" if slot else ", to the bench"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

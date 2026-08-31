#!/usr/bin/env python3
"""derive_news.py — generate deterministic factual headlines for the weekly news digest (PLAN.md §8).

state/news/2026-wNN.md is a DERIVED file (first tier only): deterministic headlines generated
from week-over-week deltas in stats, projections, matchups, and FAAB transactions. The media
agent later rewrites these in voice (R7c / R8).

Data contract (PLAN.md §8):
    state/weeks/<season>-wNN/news-facts.json = [
        {"kind": "overperformer", "text": "...", "player_id": "...", "actual": 12.4, "projected": 11.7, "delta": 0.7},
        {"kind": "underperformer", "text": "...", ...},
        {"kind": "blowout", "text": "...", "home_team": "...", "away_team": "...", "home_score": ..., "away_score": ..., "margin": ...},
        {"kind": "big_bid", "text": "...", "team": "...", "player_id": "...", "player_name": "...", "bid": ...},
        {"kind": "injury_change", "text": "...", "player_id": "...", "player_name": "...", "old_status": "...", "new_status": "..."},
    ]

Pure logic (`derive_news`) is separated from I/O so it is unit-testable with in-memory fixtures;
the CLI just loads the repo's files and writes the facts.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.scoring import score_player  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def derive_news(
    stats: dict,
    projections: dict,
    matchups: dict | None,
    transactions: list[dict],
    players: dict,
    scoring: dict,
    prior_players: dict | None = None,
    top_n: int = 3,
) -> list[dict]:
    """Derive deterministic factual headlines from committed state.

    Args:
        stats: {player_id: stat_line} for this week
        projections: {player_id: projection_row} for this week
        matchups: dict with 'matchups' key containing list of matchup dicts (or None)
        transactions: list of transaction dicts for this week (raw, unfiltered)
        players: state/players.json mapping {player_id: {name, pos, team, status, injury}}
        scoring: scoring config dict
        prior_players: prior week's players.json snapshot (for injury_change) or None
        top_n: number of top performers/bidders to include per kind

    Returns:
        List of headline dicts, grouped by kind in order: overperformer, underperformer,
        blowout, big_bid, injury_change. Deterministically sorted within each kind by
        magnitude (descending), tie-break by player_id or team slug.
    """
    headlines: list[dict] = []

    # ======================
    # Overperformer / Underperformer
    # ======================
    deltas: list[dict] = []
    for pid in stats:
        if pid not in projections:
            continue
        actual = score_player(stats[pid], scoring)
        projected = score_player(projections[pid], scoring)
        delta = round(actual - projected, 2)
        if pid in players:
            name = players[pid].get("name", pid)
        else:
            name = pid
        deltas.append({
            "player_id": pid,
            "player_name": name,
            "actual": round(actual, 2),
            "projected": round(projected, 2),
            "delta": delta,
        })

    # Sort by delta (most extreme first), tie-break by player_id
    deltas.sort(key=lambda x: (-abs(x["delta"]), x["player_id"]))

    # Top overperformers
    for d in deltas[:top_n]:
        if d["delta"] > 0:
            headlines.append({
                "kind": "overperformer",
                "text": f"{d['player_name']} outscored his projection by {d['delta']} ({d['actual']} vs {d['projected']})",
                "player_id": d["player_id"],
                "player_name": d["player_name"],
                "actual": d["actual"],
                "projected": d["projected"],
                "delta": d["delta"],
            })

    # Top underperformers
    underperf = [d for d in deltas if d["delta"] < 0]
    for d in underperf[:top_n]:
        headlines.append({
            "kind": "underperformer",
            "text": f"{d['player_name']} underscored his projection by {abs(d['delta'])} ({d['actual']} vs {d['projected']})",
            "player_id": d["player_id"],
            "player_name": d["player_name"],
            "actual": d["actual"],
            "projected": d["projected"],
            "delta": d["delta"],
        })

    # ======================
    # Blowout
    # ======================
    if matchups and "matchups" in matchups:
        blowouts: list[dict] = []
        for matchup in matchups["matchups"]:
            home_score = matchup.get("home_score", 0)
            away_score = matchup.get("away_score", 0)
            margin = abs(home_score - away_score)
            home_team = matchup.get("home")
            away_team = matchup.get("away")
            blowouts.append({
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "margin": margin,
            })

        # Sort by margin descending, tie-break by home_team
        blowouts.sort(key=lambda x: (-x["margin"], x["home_team"]))

        # Top 1-2 blowouts (just top 2 to be safe)
        for b in blowouts[:2]:
            if b["margin"] > 0:  # Only if there's an actual margin
                headlines.append({
                    "kind": "blowout",
                    "text": f"{b['home_team']} defeated {b['away_team']} {b['home_score']}-{b['away_score']}, margin {b['margin']}",
                    "home_team": b["home_team"],
                    "away_team": b["away_team"],
                    "home_score": b["home_score"],
                    "away_score": b["away_score"],
                    "margin": b["margin"],
                })

    # ======================
    # Big FAAB Bids
    # ======================
    bids: list[dict] = []
    for txn in transactions:
        if txn.get("action") == "waiver_claim":
            bid = txn.get("bid", 0)
            team = txn.get("team")
            players_list = txn.get("players", [])
            # players is an array; the first element is the add id (per schema)
            if players_list:
                added_pid = players_list[0]
                added_name = players.get(added_pid, {}).get("name", added_pid)
                bids.append({
                    "team": team,
                    "player_id": added_pid,
                    "player_name": added_name,
                    "bid": bid,
                })

    # Sort by bid descending, tie-break by team
    bids.sort(key=lambda x: (-x["bid"], x["team"]))

    for b in bids[:top_n]:
        headlines.append({
            "kind": "big_bid",
            "text": f"{b['team']} won the bid for {b['player_name']} at ${b['bid']}",
            "team": b["team"],
            "player_id": b["player_id"],
            "player_name": b["player_name"],
            "bid": b["bid"],
        })

    # ======================
    # Injury Changes
    # ======================
    if prior_players is not None:
        for pid, current_info in players.items():
            if pid not in prior_players:
                continue
            prior_info = prior_players[pid]

            curr_status = current_info.get("status")
            prior_status = prior_info.get("status")
            curr_injury = current_info.get("injury")
            prior_injury = prior_info.get("injury")

            status_changed = curr_status != prior_status
            injury_changed = curr_injury != prior_injury

            if status_changed or injury_changed:
                name = current_info.get("name", pid)
                # Build a summary of what changed
                changes = []
                if status_changed:
                    changes.append(f"status {prior_status}->{curr_status}")
                if injury_changed:
                    changes.append(f"injury {prior_injury}->{curr_injury}")
                change_text = ", ".join(changes)

                headlines.append({
                    "kind": "injury_change",
                    "text": f"{name}: {change_text}",
                    "player_id": pid,
                    "player_name": name,
                    "old_status": prior_status,
                    "new_status": curr_status,
                    "old_injury": prior_injury,
                    "new_injury": curr_injury,
                })

    return headlines


def _load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: pathlib.Path) -> list:
    """Load a JSONL file (one JSON object per line)."""
    if not path.exists():
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


def _load_scoring(config_dir: pathlib.Path) -> dict:
    path = config_dir / "scoring.json"
    if not path.exists():
        path = config_dir / "scoring.default.json"
    raw = _load_json(path, {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive state/weeks/<season>-wNN/news-facts.json")
    ap.add_argument("--week", type=int, required=True, help="week number")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    # Load state files
    players = _load_json(ROOT / "state" / "players.json", {})
    if not players:
        sys.exit("state/players.json missing or empty — run sync_sleeper.py --players first")

    week_dir = ROOT / "state" / "weeks" / f"{a.season}-w{a.week:02d}"
    stats = _load_json(week_dir / "stats.json", {})
    projections = _load_json(week_dir / "projections.json", {})
    matchups = _load_json(week_dir / "matchups.json", None)
    scoring = _load_scoring(ROOT / "config")

    # Load transactions for this week (all entries; derive_news will filter)
    transactions = _load_jsonl(ROOT / "state" / "transactions.jsonl")

    # Load prior week's players snapshot if it exists
    prior_players = None
    if a.week > 1:
        prior_players = _load_json(
            ROOT / "state" / "weeks" / f"{a.season}-w{(a.week - 1):02d}" / "players-snapshot.json",
            None,
        )

    # Derive headlines
    headlines = derive_news(stats, projections, matchups, transactions, players, scoring, prior_players)

    # Write output
    out = pathlib.Path(a.out) if a.out else (week_dir / "news-facts.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(headlines, indent=1))
    print(f"wrote {out} ({len(headlines)} headlines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

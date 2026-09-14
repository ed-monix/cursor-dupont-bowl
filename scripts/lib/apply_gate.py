"""Apply FAAB or lineups after the Commissioner gate has landed decisions/.

The Commissioner does not mutate rosters. Cloud Agents run this.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from lib.grok_dispatch import KIND_LINEUPS, KIND_WAIVERS, decision_filename


def load_ops(root: Union[str, Path]) -> dict:
    path = Path(root) / "state" / "ops" / "latest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def reversed_draft_order(rows) -> list:
    """Last pick of round 1 first — Ruling 2026-02's FAAB tiebreak proxy."""
    round_one = [r for r in rows
                 if isinstance(r, dict) and r.get("round") == 1 and r.get("team")]
    round_one.sort(key=lambda r: r.get("pick_no") or 0, reverse=True)
    seen, order = set(), []
    for row in round_one:
        team = row["team"]
        if team not in seen:
            seen.add(team)
            order.append(team)
    return order


def faab_priority_order(root, season: str = "2026"):
    """The FAAB tiebreak order, and which basis produced it.

    `state/standings.json` does not exist until week 1 has been scored, and
    faab.py raises on a contested claim whose team is missing from the order.
    state/rulings.md Ruling 2026-02 covers exactly this: until standings
    exist, ties break by reversed draft order, "at which point the normal
    record -> points-for tiebreak takes over automatically".

    Returns (order, basis) where basis is "standings" or "reversed-draft-order".
    The ruling expires on its own — the moment standings.json has teams, this
    returns the standings order without anyone editing anything.
    """
    root = Path(root)
    try:
        standings = json.loads(
            (root / "state" / "standings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        standings = {}
    if isinstance(standings, dict) and standings.get("teams"):
        return standings_worst_to_best(standings), "standings"

    rows = []
    log = root / "state" / "draft-log.jsonl"
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return [], "none"
    return reversed_draft_order(rows), "reversed-draft-order"


def standings_worst_to_best(standings: dict) -> list:
    """FAAB tiebreak order: worst record first, then lower points-for."""
    teams = (standings or {}).get("teams") or {}
    rows = []
    for slug, rec in teams.items():
        rec = rec or {}
        rows.append((
            rec.get("wins", 0),
            rec.get("ties", 0),
            rec.get("points_for", 0.0),
            slug,
        ))
    rows.sort()
    return [slug for _, _, _, slug in rows]


def collect_waiver_claims(decisions_dir: Path) -> dict:
    """{slug: claims[]} from gate files named <slug>.json (not lineup/trade)."""
    out = {}
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
        claims = obj.get("claims")
        if isinstance(claims, list):
            out[path.stem] = claims
    return out


def week_dir(root: Path, season: str, week: int) -> Path:
    return root / "state" / "weeks" / f"{season}-w{week:02d}"


def expected_decision_name(slug: str, action: str, window: Optional[str]) -> str:
    if action in ("lineups-early", "lineups-main", KIND_LINEUPS):
        win = window or ("early" if action == "lineups-early" else "main")
        return decision_filename(slug, KIND_LINEUPS, win)
    return decision_filename(slug, KIND_WAIVERS, None)

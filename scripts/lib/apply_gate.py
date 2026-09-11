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

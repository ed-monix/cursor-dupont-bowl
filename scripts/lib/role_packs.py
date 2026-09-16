"""role_packs.py — inputs for the two non-GM agents: Kris and the commissioner.

The GM packs (lib/packs.py) are built to be starved: a GM sees its own file and
the public board, nothing else. These two roles are the opposite problem — each
is allowed MORE than a GM, but a different more, and the difference is a rule
rather than a convenience:

  media (Kris Jenner)
      Public record ONLY (agents/media.md "What you read"): derived headlines,
      the week's buzz file, the forum, last week's recap, standings, logged
      transactions, team press. She NEVER sees a `general-manager.md`. She has
      no powers, so the only thing protecting the league from her is what she
      is handed. Buzz goes to her and stops there — GMs only ever see her
      rewrite.

  commissioner
      Everything, including every team's `general-manager.md`. CLAUDE.md rule 1
      names it the sole exception, "chat only, never GM files left on the shared
      Bot disk". Passing them in the prompt is that chat path: the turn runs in
      a temp directory that is destroyed when it returns, and nothing is
      written anywhere a GM could reach.

Missing inputs are omitted rather than faked. A week with no recap yet, no buzz
and no forum is a legal week-1 state, not an error.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

WEEK_FILE = "{season}-w{week:02d}"


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_jsonl(path: Path) -> list:
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _label(season: str, week: int) -> str:
    return WEEK_FILE.format(season=season, week=week)


def team_slugs(root: Path) -> list:
    teams = root / "teams"
    if not teams.is_dir():
        return []
    return sorted(p.name for p in teams.iterdir()
                  if p.is_dir() and not p.name.startswith("_"))


def transactions_for_week(root: Path, week: int, season: str) -> list:
    rows = _read_jsonl(root / "state" / "transactions.jsonl")
    keep = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("season", season)) != str(season):
            continue
        if row.get("week") in (week, str(week)):
            keep.append(row)
    return keep


def build_media_pack(root: Union[str, Path], week: int,
                     season: str = "2026") -> dict:
    """Public record only. Never a GM file — see agents/media.md."""
    root = Path(root)
    label = _label(season, week)
    prev = _label(season, week - 1) if week > 1 else None
    week_dir = root / "state" / "weeks" / label

    press = {}
    for slug in team_slugs(root):
        text = _read_text(root / "teams" / slug / "press" / f"{label}.md")
        if text.strip():
            press[slug] = text

    pack = {
        "season": season,
        "week": week,
        "news_facts": _read_json(week_dir / "news-facts.json", {}),
        "buzz": _read_text(root / "state" / "news" / "buzz" / f"{label}.md"),
        "forum_this_week": _read_jsonl(root / "state" / "forum" / f"{label}.jsonl"),
        "standings": _read_json(root / "state" / "standings.json", {}),
        "transactions_this_week": transactions_for_week(root, week, season),
        "press": press,
    }
    if prev:
        pack["last_week_forum"] = _read_jsonl(
            root / "state" / "forum" / f"{prev}.jsonl")
        pack["last_recap"] = _read_text(
            root / "state" / "weeks" / prev / "recap.md")
    return pack


def build_commissioner_pack(root: Union[str, Path], week: int,
                            season: str = "2026", stage: str = "waivers",
                            window: Optional[str] = None,
                            include_gm_files: bool = True) -> dict:
    """Everything the commissioner needs for one stage, GM files included.

    include_gm_files=False exists for tests and for anyone who wants to prove a
    given turn never saw them; the real runs leave it on, because the collusion
    call in agents/commissioner.md cannot be made without them.
    """
    root = Path(root)
    label = _label(season, week)
    week_dir = root / "state" / "weeks" / label

    pack = {
        "season": season,
        "week": week,
        "stage": stage,
        "window": window,
        "standings": _read_json(root / "state" / "standings.json", {}),
        "league_board": _read_json(root / "state" / "league-board.json", {}),
        "rulings": _read_text(root / "state" / "rulings.md"),
        "forum_this_week": _read_jsonl(root / "state" / "forum" / f"{label}.jsonl"),
    }

    decisions = {}
    dec_dir = week_dir / "decisions"
    if dec_dir.is_dir():
        for path in sorted(dec_dir.glob("*.json")):
            decisions[path.name] = _read_json(path, {})
    pack["decisions"] = decisions

    if stage == "waivers":
        pack["faab_report_dry_run"] = _read_json(week_dir / "faab-report.json", {})
        # Every outgoing offer and the harness's verdict on it, so a blocked
        # trade is reviewable rather than invisible.
        pack["trade_screen"] = _read_json(week_dir / "trade-screen.json", [])
    elif stage == "lineups":
        pack["lineups"] = _read_json(week_dir / "lineups.json", {})
    elif stage == "recap":
        pack["matchups"] = _read_json(week_dir / "matchups.json", {})
        pack["transactions_this_week"] = transactions_for_week(root, week, season)
        pack["reconciliation"] = _read_json(week_dir / "reconciliation.json", [])
        lineups = _read_json(week_dir / "lineups.json", {}) or {}
        pack["fallback_teams"] = sorted(
            slug for slug, side in lineups.items()
            if isinstance(side, dict) and side.get("fallback")
        )

    if include_gm_files:
        # CLAUDE.md rule 1: the commissioner is the sole agent permitted these,
        # and only in chat. This turn runs in a temp dir that is destroyed on
        # return, so nothing is left anywhere a GM could reach.
        pack["general_manager_files"] = {
            slug: _read_text(root / "teams" / slug / "general-manager.md")
            for slug in team_slugs(root)
        }
    return pack

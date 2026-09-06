#!/usr/bin/env python3
"""gm_dossier.py — GM memory: the press file (write) and the dossier (read).

Review 2026-08-31, recommendation R1: give every GM a past it can hold a
grudge about. Two halves, both pure file I/O, stdlib only:

- `append_press(root, slug, week, entry, season)` — WRITE memory. After a
  Saturday/Sunday run the harness appends that GM's public output (its
  `note_reply`, logged claim/trade/lineup reasoning, an outcome line once
  known) to `teams/<slug>/press/<season>-w<NN>.md` (PLAN.md §8). Only ever
  touches that one team's own press directory.

- `build_dossier(root, slug, season, current_week, weeks_back)` — READ
  memory. Assembles a bounded, curated dict of THIS TEAM's own past — the
  owner-note/GM-reply thread, its own transaction history, recap lines that
  name it, and its record trajectory — for the harness to inject into that
  team's Saturday/Sunday context. A dossier, not a dump: every list is capped
  (see the CAP_* constants below).

Isolation (CLAUDE.md rule 1): a GM subagent may see ONLY its own
`general-manager.md`, never another team's. This module never reads *any*
`general-manager.md` at all (that file isn't memory, it's static strategy —
out of scope here), and every path it touches is derived from the single
`slug` argument plus repo-global public record (`state/`) — there is no code
path in this file that can reach another team's `teams/<other-slug>/` folder.
Everything a dossier can possibly contain is therefore either this team's own
output (its notes/replies, its own transactions, its own press) or the
public record (recaps, standings, matchups) that every team can already see.

Both functions are robust to missing files/dirs: they create what they need
to write, and they return empty lists/dicts (never raise) for anything that
isn't there yet to read — this repo is pre-season and most of `state/` and
`teams/*/notes|press/` won't exist until the league is actually running.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Optional, Union

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Bounds -- keep the dossier a *dossier*, not a dump (review R1: "bounded,
# curated, cheap in tokens"). weeks_back also governs the notes/recap window
# and is caller-configurable; these two are hard caps on top of that.
CAP_TRANSACTIONS = 10
CAP_RECAP_MENTIONS = 15

_PRESS_SEPARATOR = "\n\n---\n\n"

# teams/<slug>/notes/<season>-w<NN>.md and teams/<slug>/press/<season>-w<NN>.md
_WEEK_FILE_RE = re.compile(r"^(?P<season>\d{4})-w(?P<week>\d{2})\.md$")
# state/weeks/<season>-w<NN>/ (a directory, holds recap.md / matchups.json / ...)
_WEEK_DIR_RE = re.compile(r"^(?P<season>\d{4})-w(?P<week>\d{2})$")


def _week_str(week: Union[int, str]) -> str:
    """Zero-pad a week number to the league's 'wNN' filename convention."""
    try:
        return f"{int(week):02d}"
    except (TypeError, ValueError):
        return str(week)


def _read_text(path: pathlib.Path) -> str:
    """Read a text file, or '' if it doesn't exist / can't be read. Never raises."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Deliverable 1: write memory -- the press file
# ---------------------------------------------------------------------------

def append_press(root: Union[str, pathlib.Path], slug: str, week: Union[int, str],
                  entry: str, season: str = "2026") -> pathlib.Path:
    """Append `entry` to teams/<slug>/press/<season>-w<NN>.md, creating it if needed.

    `entry` is one already-formatted markdown block from the caller: a
    GM's `note_reply`, its logged claim/trade/lineup reasoning, or an outcome
    line ("won the bid at $23", "lineup fell back -- Hall of Shame"). This
    function does no formatting of its own beyond stripping surrounding
    blank lines.

    Only ever touches `teams/<slug>/press/` for the one `slug` passed in --
    it never opens, lists, or infers anything about any other team's folder.

    Idempotent-friendly: repeated calls (e.g. a Saturday run's note_reply,
    then that same week's outcome once FAAB resolves) each land as their own
    block, separated by a horizontal rule, rather than being silently
    dropped or run together into unparseable prose. It does not de-duplicate
    identical text -- callers that must not double-log an outcome are
    responsible for that themselves (this is a pure append).

    Returns the path written to.
    """
    root = pathlib.Path(root)
    press_dir = root / "teams" / slug / "press"
    press_dir.mkdir(parents=True, exist_ok=True)
    path = press_dir / f"{season}-w{_week_str(week)}.md"

    entry_text = str(entry).strip("\n")
    existing = _read_text(path)
    if existing:
        new_text = existing + _PRESS_SEPARATOR + entry_text + "\n"
    else:
        new_text = entry_text + "\n"

    path.write_text(new_text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Deliverable 2: read memory -- the dossier
# ---------------------------------------------------------------------------

def _as_int_week(week: Any) -> Optional[int]:
    if week is None:
        return None
    try:
        return int(week)
    except (TypeError, ValueError):
        return None


def _recent_week_numbers(dir_path: pathlib.Path, season: str, current_week: Optional[int],
                          weeks_back: int, pattern: re.Pattern) -> list:
    """Week numbers found under dir_path for `season`, ascending, capped to the
    most recent `weeks_back`.

    If `current_week` is given, only weeks strictly before it are eligible --
    the dossier is the team's PAST (what it can hold a grudge about), not the
    week currently being decided. Missing/unreadable dir -> [].
    """
    if weeks_back is None or weeks_back <= 0:
        return []
    try:
        if not dir_path.is_dir():
            return []
        children = list(dir_path.iterdir())
    except OSError:
        return []

    weeks = []
    for child in children:
        m = pattern.match(child.name)
        if not m or m.group("season") != str(season):
            continue
        wk = int(m.group("week"))
        if current_week is not None and wk >= current_week:
            continue
        weeks.append(wk)
    weeks.sort()
    return weeks[-weeks_back:]


def _team_display_names(team_dir: pathlib.Path, slug: str) -> list:
    """Strings that count as 'naming this team' in prose: the slug, the slug
    with hyphens turned to spaces, and (if readable) this team's OWN
    roster.json 'team' display name. Never reads another team's files.
    """
    needles = {slug, slug.replace("-", " ")}
    try:
        roster = json.loads((team_dir / "roster.json").read_text(encoding="utf-8"))
        name = roster.get("team")
        if isinstance(name, str) and name.strip():
            needles.add(name.strip())
    except (OSError, ValueError):
        pass
    return sorted(n for n in needles if n)


def _mentions_team(line: str, needles: list) -> bool:
    """Whole-word (or whole-phrase), case-insensitive match against any needle.

    Word-boundary matching avoids the obvious false positive of a slug/name
    being a substring of an unrelated word (e.g. slug 'fox' inside 'foxtrot').
    Multi-word display names ('Team One') match as a phrase via \\b on each end.
    """
    for needle in needles:
        if re.search(r"\b" + re.escape(needle) + r"\b", line, re.IGNORECASE):
            return True
    return False


def _collect_notes(team_dir: pathlib.Path, season: str, current_week: Optional[int],
                    weeks_back: int) -> list:
    """Last `weeks_back` owner-note weeks: the note text and the GM's reply.

    PLAN.md §8 defines `teams/*/notes/2026-wNN.md` as the owner note PLUS the
    GM's reply in the same file, and `teams/*/press/2026-wNN.md` as the GM's
    separately-logged public statements for that week. A command may write
    the reply into either place, so this reads both for each note week and
    hands back whatever exists -- most recent last, so the feud thread reads
    in order.
    """
    notes_dir = team_dir / "notes"
    press_dir = team_dir / "press"
    weeks = _recent_week_numbers(notes_dir, season, current_week, weeks_back, _WEEK_FILE_RE)

    entries = []
    for wk in weeks:
        wk_str = _week_str(wk)
        entries.append({
            "week": wk,
            "note": _read_text(notes_dir / f"{season}-w{wk_str}.md"),
            "press": _read_text(press_dir / f"{season}-w{wk_str}.md"),
        })
    return entries


def _collect_own_transactions(root: pathlib.Path, slug: str, cap: int) -> list:
    """This team's own slice of state/transactions.jsonl, last `cap` entries.

    Each entry is whatever was logged (PLAN.md §8 /
    docs/schemas/transaction-entry.json): timestamp, team, action, players,
    bid, reasoning, status. Filtered strictly by entry["team"] == slug --
    another team's entries in the same file are never included.
    """
    path = root / "state" / "transactions.jsonl"
    text = _read_text(path)
    if not text:
        return []

    matches = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("team") == slug:
            matches.append(entry)

    return matches[-cap:] if cap else matches


def _collect_recap_mentions(root: pathlib.Path, team_dir: pathlib.Path, slug: str, season: str,
                             current_week: Optional[int], weeks_back: int, cap: int) -> list:
    """Lines from the last `weeks_back` state/weeks/<season>-wNN/recap.md files
    that mention this team by slug or display name -- grudge fuel. Capped at
    `cap` total lines across all weeks scanned.
    """
    weeks_dir = root / "state" / "weeks"
    weeks = _recent_week_numbers(weeks_dir, season, current_week, weeks_back, _WEEK_DIR_RE)
    needles = _team_display_names(team_dir, slug)

    mentions = []
    for wk in weeks:
        text = _read_text(weeks_dir / f"{season}-w{_week_str(wk)}" / "recap.md")
        if not text:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and _mentions_team(stripped, needles):
                mentions.append({"week": wk, "line": stripped})
                if len(mentions) >= cap:
                    return mentions
    return mentions


def _collect_trajectory(root: pathlib.Path, slug: str, season: str,
                         current_week: Optional[int], weeks_back: int) -> dict:
    """Current standing from state/standings.json, plus (if the week's
    matchups.json exists) the last `weeks_back` results: opponent, own/opp
    score, and W/L/T.
    """
    record: dict = {}
    standings_text = _read_text(root / "state" / "standings.json")
    if standings_text:
        try:
            standings = json.loads(standings_text)
            record = (standings.get("teams") or {}).get(slug) or {}
        except (json.JSONDecodeError, ValueError, AttributeError):
            record = {}

    weeks_dir = root / "state" / "weeks"
    weeks = _recent_week_numbers(weeks_dir, season, current_week, weeks_back, _WEEK_DIR_RE)

    results = []
    for wk in weeks:
        text = _read_text(weeks_dir / f"{season}-w{_week_str(wk)}" / "matchups.json")
        if not text:
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        for m in data.get("matchups", []) if isinstance(data, dict) else []:
            if m.get("home") == slug:
                opponent, own_score, opp_score = m.get("away"), m.get("home_score"), m.get("away_score")
            elif m.get("away") == slug:
                opponent, own_score, opp_score = m.get("home"), m.get("away_score"), m.get("home_score")
            else:
                continue
            winner = m.get("winner")
            if winner == slug:
                result = "W"
            elif winner == "tie":
                result = "T"
            elif winner is not None:
                result = "L"
            else:
                result = None
            results.append({
                "week": wk, "opponent": opponent, "result": result,
                "score": own_score, "opponent_score": opp_score,
            })

    return {"record": record, "recent_results": results}


def _collect_last_week_player_stats(root: pathlib.Path, slug: str, season: str,
                                     current_week: Optional[int]) -> dict:
    """Per-starter raw stat lines for this team's most recent scored week.

    Several GM biases trigger on box-score EVENTS, not points ("he fumbled
    on me", "a costly pick") -- matchups.json carries per-player points only,
    so this joins the team's most recent lineup (home_lineup/away_lineup)
    against that same week's stats.json for the raw lines.

    Returns {"week": int, "players": {player_id: {"points": float,
    "stats": {raw stat keys...}}}} for the newest week that has both files
    and this team in a matchup, or {} when there is no such week yet.
    """
    weeks_dir = root / "state" / "weeks"
    weeks = _recent_week_numbers(weeks_dir, season, current_week, 1, _WEEK_DIR_RE)

    for wk in reversed(weeks):  # newest first
        week_dir = weeks_dir / f"{season}-w{_week_str(wk)}"
        matchups_text = _read_text(week_dir / "matchups.json")
        stats_text = _read_text(week_dir / "stats.json")
        if not matchups_text:
            continue
        try:
            data = json.loads(matchups_text)
            stats = json.loads(stats_text) if stats_text else {}
        except (json.JSONDecodeError, ValueError):
            continue

        for m in data.get("matchups", []) if isinstance(data, dict) else []:
            if m.get("home") == slug:
                lineup = m.get("home_lineup") or {}
            elif m.get("away") == slug:
                lineup = m.get("away_lineup") or {}
            else:
                continue
            players = {
                pid: {"points": pts, "stats": stats.get(pid, {}) or {}}
                for pid, pts in lineup.items()
            }
            return {"week": wk, "players": players}

    return {}


def build_dossier(root: Union[str, pathlib.Path], slug: str, season: str = "2026",
                   current_week: Optional[Union[int, str]] = None, weeks_back: int = 3) -> dict:
    """Assemble THIS TEAM's own bounded context: the feud thread, its own
    transactions, recap lines naming it, and its trajectory.

    Returns:
        {
          "team": slug,
          "season": season,
          "notes":  [{"week": int, "note": str, "press": str}, ...]   # <= weeks_back, oldest first
          "own_transactions": [ {...transaction-entry...}, ... ]      # <= 10, oldest first
          "recap_mentions": [ {"week": int, "line": str}, ... ]       # <= 15
          "trajectory": {
              "record": {"wins": int, "losses": int, "ties": int,
                         "points_for": float, "points_against": float} or {},
              "recent_results": [
                  {"week": int, "opponent": str, "result": "W"|"L"|"T"|None,
                   "score": float, "opponent_score": float}, ...
              ]  # <= weeks_back
          },
          "last_week_player_stats": {          # {} until a week is scored
              "week": int,
              "players": {player_id: {"points": float, "stats": {...raw}}}
          }
        }

    Pure file reads; robust to a missing repo, missing team, or missing
    state -- every field defaults to [] / {} rather than raising. `weeks_back`
    bounds both the notes and the recap window (and, incidentally, the
    trajectory's recent-results window); transactions and recap_mentions
    additionally cap at CAP_TRANSACTIONS / CAP_RECAP_MENTIONS regardless of
    weeks_back.

    Isolation: only ever reads under teams/<slug>/ (this team) and state/
    (public record) -- see the module docstring.
    """
    root = pathlib.Path(root)
    team_dir = root / "teams" / slug
    week_int = _as_int_week(current_week)
    try:
        weeks_back = int(weeks_back)
    except (TypeError, ValueError):
        weeks_back = 3

    try:
        notes = _collect_notes(team_dir, season, week_int, weeks_back)
    except Exception:
        notes = []

    try:
        own_transactions = _collect_own_transactions(root, slug, CAP_TRANSACTIONS)
    except Exception:
        own_transactions = []

    try:
        recap_mentions = _collect_recap_mentions(
            root, team_dir, slug, season, week_int, weeks_back, CAP_RECAP_MENTIONS)
    except Exception:
        recap_mentions = []

    try:
        trajectory = _collect_trajectory(root, slug, season, week_int, weeks_back)
    except Exception:
        trajectory = {"record": {}, "recent_results": []}

    # Raw stat lines for the last scored week's own starters, so event-keyed
    # grudges (fumbles, costly picks) have something concrete to fire on.
    try:
        last_week_player_stats = _collect_last_week_player_stats(
            root, slug, season, week_int)
    except Exception:
        last_week_player_stats = {}

    # This team's own seeded opinions of the rest of the cast (R10) — priors the
    # lived record then layers on top. Its OWN file only; isolation holds.
    opinions = {}
    try:
        op = pathlib.Path(root) / "teams" / slug / "opinions.json"
        if op.exists():
            with open(op, encoding="utf-8") as f:
                opinions = json.load(f)
    except Exception:
        opinions = {}

    return {
        "team": slug,
        "season": season,
        "notes": notes,
        "own_transactions": own_transactions,
        "recap_mentions": recap_mentions,
        "trajectory": trajectory,
        "last_week_player_stats": last_week_player_stats,
        "opinions": opinions,
    }


def _main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Print a team's GM dossier (memory: notes/replies, own "
                    "transactions, recap mentions, trajectory) as JSON.")
    parser.add_argument("--team", required=True, help="team slug, e.g. 'team-chaos'")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--week", type=int, default=None,
                         help="current week; only weeks strictly before this are included")
    parser.add_argument("--weeks-back", type=int, default=3)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    dossier = build_dossier(args.root, args.team, season=args.season,
                             current_week=args.week, weeks_back=args.weeks_back)
    print(json.dumps(dossier, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())

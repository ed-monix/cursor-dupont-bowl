#!/usr/bin/env python3
"""buzz_inbox.py — normalize a dropped X buzz file into the canonical path.

Third source for `state/news/buzz/<season>-wNN.md`, alongside
`fetch_buzz.py`'s manual-paste and xAI-API modes:

    The owner runs an external Grok automation (a SuperGrok subscription
    pulling X sentiment outside this repo — NOT the paid xAI API, and
    unrelated to GROK_API_KEY) that commits a markdown file directly into
    `state/news/buzz/inbox/`. It does not know the league week number.

This script consumes that inbox:

    1. CANONICAL FILE EXISTS: if `state/news/buzz/<season>-wNN.md` already
       exists and is non-empty, it wins — the inbox is left untouched and
       nothing is written.
    2. INBOX HAS A FILE: else, take the most recently modified `*.md`/`*.txt`
       file in the inbox (ignoring README.md and .gitkeep), stamp it with the
       same header shape `fetch_buzz.py` writes in API mode (source: inbox),
       write it to the canonical path, and remove the consumed inbox file.
    3. INBOX EMPTY: else, nothing to do — the run proceeds without buzz.

Hard rule (config/league-rules.md): Sleeper is the sole source of FACTS
(injury status, scores, rosters). Buzz is public sentiment for the tabloid —
no script reads it, no validator trusts it, and GMs only ever see it after
Kris rewrites it into `state/news/<season>-wNN.md`.

Like `fetch_buzz.py`, this script NEVER blocks a league run: every path
prints a note and exits 0, including a missing/empty inbox.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
IGNORED_NAMES = {"README.md", ".gitkeep"}
INBOX_SUFFIXES = {".md", ".txt"}


def inbox_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "state" / "news" / "buzz" / "inbox"


def buzz_path(root: pathlib.Path, week: int, season: str = "2026") -> pathlib.Path:
    return root / "state" / "news" / "buzz" / f"{season}-w{week:02d}.md"


def _candidate_files(inbox: pathlib.Path) -> list[pathlib.Path]:
    if not inbox.is_dir():
        return []
    return [
        p for p in inbox.iterdir()
        if p.is_file() and p.name not in IGNORED_NAMES and p.suffix.lower() in INBOX_SUFFIXES
    ]


def normalize_inbox(root: pathlib.Path, week: int, season: str = "2026",
                     dry_run: bool = False) -> tuple[str, str]:
    """Consume the inbox into the canonical buzz path if appropriate.

    Returns (status, detail) where status is one of:
        "canonical-exists" — canonical file already present, inbox untouched
        "empty"            — no usable file in the inbox, nothing to do
        "normalized"       — inbox file stamped and written (or would be, on
                              a dry run), source inbox file removed (unless
                              dry_run)
    """
    canonical = buzz_path(root, week, season)
    if canonical.exists() and canonical.read_text(encoding="utf-8").strip():
        return "canonical-exists", str(canonical)

    candidates = _candidate_files(inbox_dir(root))
    if not candidates:
        return "empty", str(inbox_dir(root))

    source = max(candidates, key=lambda p: p.stat().st_mtime)
    content = source.read_text(encoding="utf-8").strip()

    header = (
        f"# X buzz — {season} week {week:02d} (source: inbox)\n\n"
        "<!-- Sentiment only. Sleeper remains the sole source of facts; the\n"
        "tabloid may spin this, no script or validator ever reads it. -->\n\n"
    )

    if dry_run:
        return "normalized", f"{source} -> {canonical} (dry run, nothing written)"

    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(header + content + "\n", encoding="utf-8")
    source.unlink()
    return "normalized", f"{source} -> {canonical}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Normalize a dropped inbox file into the canonical "
                    "weekly buzz path (canonical file wins if present, "
                    "empty inbox is a silent no-op — never blocks the run).")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true",
                     help="report what would happen without writing or "
                          "deleting anything")
    args = ap.parse_args()

    status, detail = normalize_inbox(args.root, args.week, args.season,
                                      dry_run=args.dry_run)
    if status == "canonical-exists":
        print(f"buzz-inbox: canonical file already present ({detail}); inbox left untouched")
    elif status == "empty":
        print(f"buzz-inbox: nothing in inbox ({detail}); run proceeds without buzz")
    else:
        print(f"buzz-inbox: normalized {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

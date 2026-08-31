#!/usr/bin/env python3
"""forum.py — trash-talk forum plumbing (PLAN.md §8 R6).

state/forum/<season>-wNN.jsonl is append-only weekly trash-talk thread,
one post per entry: {timestamp, team, post}. At most one post per team per run.

Pure logic separated from I/O for testability; stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys


def append_post(root: pathlib.Path | str, week: int, team: str, post: str,
                season: str = "2026", timestamp: str | None = None) -> None:
    """Append one post to state/forum/<season>-w<NN>.jsonl.

    Arguments:
        root: repository root (contains state/ directory)
        week: week number (1-17, formatted as zero-padded two digits)
        team: team slug (e.g., "team-a")
        post: post text (the trash talk)
        season: season year (default "2026")
        timestamp: ISO8601 timestamp; if None, uses current UTC time

    Raises ValueError if the team already posted in this week's thread
    (one post per team per run).
    """
    root = pathlib.Path(root)
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Check if the team already posted this week.
    existing_posts = read_thread(root, week, season)
    for post_obj in existing_posts:
        if post_obj["team"] == team:
            raise ValueError(
                f"Team {team} already posted in week {week} forum; "
                f"at most one post per team per run"
            )

    # Create state/forum/ directory if needed.
    forum_dir = root / "state" / "forum"
    forum_dir.mkdir(parents=True, exist_ok=True)

    # Append to the JSONL file.
    filename = f"{season}-w{week:02d}.jsonl"
    filepath = forum_dir / filename
    entry = {"timestamp": timestamp, "team": team, "post": post}
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_thread(root: pathlib.Path | str, week: int, season: str = "2026") -> list[dict]:
    """Return the week's forum posts in order, one dict per post.

    {timestamp, team, post} for each line in state/forum/<season>-wNN.jsonl.
    Returns empty list if the file does not exist or is empty.

    Arguments:
        root: repository root (contains state/ directory)
        week: week number (1-17)
        season: season year (default "2026")
    """
    root = pathlib.Path(root)
    filename = f"{season}-w{week:02d}.jsonl"
    filepath = root / "state" / "forum" / filename

    if not filepath.exists():
        return []

    posts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:  # Skip empty lines
                posts.append(json.loads(line))
    return posts


def main() -> int:
    """CLI for testing/manual append. Not used by the harness."""
    ap = argparse.ArgumentParser(description="Forum post plumbing")
    ap.add_argument("--root", default=".", help="Repository root")
    ap.add_argument("--week", type=int, required=True, help="Week number")
    ap.add_argument("--team", help="Team slug (required for append)")
    ap.add_argument("--post", help="Post text (required for append)")
    ap.add_argument("--season", default="2026", help="Season year")
    ap.add_argument("--read", action="store_true", help="Read thread instead of appending")
    a = ap.parse_args()

    root = pathlib.Path(a.root)
    if a.read:
        thread = read_thread(root, a.week, a.season)
        print(json.dumps(thread, indent=2))
        return 0

    if not a.team or not a.post:
        ap.error("--team and --post are required when not using --read")

    try:
        append_post(root, a.week, a.team, a.post, a.season)
        print(f"Appended post from {a.team} to week {a.week}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

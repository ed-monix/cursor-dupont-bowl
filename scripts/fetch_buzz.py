#!/usr/bin/env python3
"""fetch_buzz.py — weekly X/NFL buzz for the tabloid (sentiment ONLY, never facts).

Dual-mode source for `state/news/buzz/<season>-wNN.md`, the optional third
input to the Media Mogul's weekly digest (alongside derive_news.py's
deterministic facts and owner-planted rumors):

    1. MANUAL: if the buzz file already exists (the owner asked Grok in the
       app and pasted the result), it is left untouched and used as-is.
    2. API: else, if GROK_API_KEY is set, one call to the xAI API with live
       X search asks for the week's NFL fantasy storylines + sentiment and
       writes the file.
    3. FALLBACK: else (no file, no key, or the call fails for ANY reason),
       no file is written and the tabloid runs on derived + planted material
       alone. This script NEVER blocks a league run: every failure path
       prints a note and exits 0.

Hard rule (config/league-rules.md): Sleeper is the sole source of FACTS
(injury status, scores, rosters). Buzz is public sentiment for the tabloid —
no script reads it, no validator trusts it, and GMs only ever see it after
Kris rewrites it into `state/news/<season>-wNN.md`.

Env: GROK_API_KEY (required for API mode), GROK_MODEL (default "grok-4"),
GROK_API_URL (default https://api.x.ai/v1/chat/completions — override for
tests or proxies).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4"
TIMEOUT_SECONDS = 90

PROMPT = (
    "List the 10-15 biggest NFL fantasy football storylines and player buzz "
    "on X from the past week, for week {week} of the {season} season. For "
    "each: one markdown bullet naming the player or team, what people are "
    "saying, and the overall sentiment (hyped / worried / furious / mocking "
    "/ divided). Plain markdown bullets only, no preamble, no conclusion. "
    "These are used as tabloid material for an entertainment league — "
    "storylines and sentiment, not injury reports or lineup advice."
)


def buzz_path(root: pathlib.Path, week: int, season: str = "2026") -> pathlib.Path:
    return root / "state" / "news" / "buzz" / f"{season}-w{week:02d}.md"


def fetch_from_api(week: int, season: str, api_key: str,
                    model: str | None = None, api_url: str | None = None) -> str:
    """One xAI chat-completions call with live X search. Returns the model's
    text. Raises on any HTTP/shape problem — the caller decides that failure
    means 'no buzz this week', never a crashed run."""
    body = {
        "model": model or os.environ.get("GROK_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "user", "content": PROMPT.format(week=week, season=season)},
        ],
        "search_parameters": {
            "mode": "on",
            "sources": [{"type": "x"}],
            "max_search_results": 25,
        },
    }
    resp = requests.post(
        api_url or os.environ.get("GROK_API_URL", DEFAULT_API_URL),
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty completion content")
    return content.strip()


def gather_buzz(root: pathlib.Path, week: int, season: str = "2026") -> tuple[str, str]:
    """Ensure the week's buzz file exists if a source is available.

    Returns (status, detail) where status is one of:
        "manual"  — file already present (owner-pasted), left untouched
        "api"     — fetched via the xAI API and written
        "skipped" — no manual file and no usable API (missing key or the
                    call failed); nothing written, run proceeds without buzz
    """
    path = buzz_path(root, week, season)
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return "manual", str(path)

    api_key = os.environ.get("GROK_API_KEY", "").strip()
    if not api_key:
        return "skipped", "no manual buzz file and GROK_API_KEY not set"

    try:
        content = fetch_from_api(week, season, api_key)
    except Exception as e:  # any failure = no buzz, never a blocked run
        return "skipped", f"xAI API call failed ({e.__class__.__name__}: {e})"

    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# X buzz — {season} week {week:02d} (source: grok live search)\n\n"
        "<!-- Sentiment only. Sleeper remains the sole source of facts; the\n"
        "tabloid may spin this, no script or validator ever reads it. -->\n\n"
    )
    path.write_text(header + content + "\n", encoding="utf-8")
    return "api", str(path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gather the week's X buzz for the tabloid (manual file "
                    "first, xAI API if GROK_API_KEY is set, silent skip "
                    "otherwise — never blocks the run).")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    args = ap.parse_args()

    status, detail = gather_buzz(ROOT, args.week, args.season)
    if status == "manual":
        print(f"buzz: using owner-pasted file {detail}")
    elif status == "api":
        print(f"buzz: fetched via xAI live search -> {detail}")
    else:
        print(f"buzz: none this week ({detail}); tabloid runs on derived + planted material")
    return 0


if __name__ == "__main__":
    sys.exit(main())

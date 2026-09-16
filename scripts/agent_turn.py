#!/usr/bin/env python3
"""agent_turn.py — the two non-GM turns: Kris's tabloid and the commissioner.

    python scripts/agent_turn.py --role media --week 2
    python scripts/agent_turn.py --role commissioner --week 2 --stage waivers
    python scripts/agent_turn.py --role commissioner --week 2 --stage lineups --window main
    python scripts/agent_turn.py --role commissioner --week 2 --stage recap
    python scripts/agent_turn.py --role media --week 2 --dry-run

Same transport as scripts/gm_turn.py — an isolated `claude -p` in an empty
directory — but these are single turns, not a twelve-way fan-out, and they run
on Opus rather than Sonnet. That split is deliberate: the GM turns are 36
constrained JSON decisions a week and Sonnet does them well; the tabloid and
the recap are one turn each on much smaller input, and they are the part of
this league a human actually reads. Downgrading them saves almost nothing and
costs the product.

Who may see what is enforced by which pack a role gets (scripts/lib/role_packs.py):
Kris gets the public record and never a `general-manager.md`; the commissioner
gets everything, which CLAUDE.md rule 1 permits it alone, in chat only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import role_packs  # noqa: E402
from lib.claude_turn import TurnError, run_turn, usage_line  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

DEFAULT_MODEL = "claude-opus-5"

MEDIA_CONTRACT = """
## Your output

Write this week's tabloid front page as markdown. That markdown IS your entire
reply — no preamble, no "here is the article", no code fence around it, no
commentary after it. It is written straight to the file every GM in the league
reads before they move.

Rules that are not yours to bend:

- Sleeper is the sole source of FACTS. Scores, injuries and rosters come from
  the derived headlines in your pack. You may spin motive, grudge and meaning
  however you like — you may not invent a stat, a transaction, or an injury.
- The buzz in your pack is real-world X sentiment about real NFL players. It is
  atmosphere. Never present it as a league fact and never quote it as though a
  GM said it.
- You have no powers. You cannot rule, void, fine or block. If you catch
  something that smells illegal, you write about it; the commissioner decides.
- You have never read a GM's file and you do not have one here. Report their
  motives with total confidence anyway.

Keep it to a page. Give the week a story.
"""

COMMISSIONER_CONTRACT = {
    "waivers": """
## Your output

Write your pre-apply signoff as markdown. That markdown IS your entire reply —
no preamble, no fence, no commentary around it.

You are reviewing the twelve decision objects and the FAAB dry-run in your pack,
before anything is applied. Cover, in your own dry voice:

- every decision you BLOCK and the specific rule it breaks (over-budget bids,
  nonexistent or already-rostered players, a second outgoing trade offer, a
  trade after the week-11 deadline, output that already failed its retry),
- anything legal that you dislike, clearly marked as editorial rather than a
  ruling — lopsided trades, ruinous bids and spite are protected,
- any `fallback: true` team,
- a final line stating whether the run may proceed.

If you block nothing, say so plainly. Blocking nothing is the normal outcome.
""",
    "lineups": """
## Your output

Write your lineup signoff as markdown. That markdown IS your entire reply.

Confirm every lineup is legal: slot eligibility, no duplicates, nobody moved
whose NFL game has kicked off, nothing touched that locked in an earlier
window. Note every `fallback: true` team. Do not second-guess a legal benching
of a stud — a GM is allowed to be wrong on purpose. End with whether the window
may be frozen.
""",
    "recap": """
## Your output

Write the week's recap as markdown. That markdown IS your entire reply — it is
written straight to `recap.md`, which is what the owners read before they write
next week's notes.

It must contain:

- results with scores and a one-line note per game,
- the single best and single worst decision of the week, quoting the GM's own
  logged reasoning against them where deserved,
- **Most In-Character Move of the Week** — the move that most expressed a GM's
  stated personality, quoting its reasoning,
- **Least In-Character Move** — its inverse: whoever quietly started the highest
  projection at every slot and made the safe, boring play gets named for it.
  Publicly scoring blandness is what stops twelve agents collapsing into one
  optimizer, so do not skip this one for politeness,
- the **Hall of Shame**: every `fallback: true` team,
- **Quote of the Week** from the forum thread,
- trade and waiver commentary — flag lopsided-but-legal moves, never void them,
- the current standings table,
- any live-vs-final drift worth mocking,
- a closing line of weary editorial.

Under a page. Dry, procedural, faintly funereal. Never an exclamation point.
""",
}

OUTPUT_PATH = {
    ("media", None): "state/news/{label}.md",
    ("commissioner", "waivers"): "state/weeks/{label}/commissioner-signoff.md",
    ("commissioner", "lineups"): "state/weeks/{label}/commissioner-signoff-{window}.md",
    ("commissioner", "recap"): "state/weeks/{label}/recap.md",
}


def persona(root: pathlib.Path, role: str) -> str:
    name = "media.md" if role == "media" else "commissioner.md"
    path = root / "agents" / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"agent_turn: cannot read {path}: {e}")


def build(root: pathlib.Path, role: str, week: int, season: str,
          stage: str | None, window: str | None) -> tuple:
    if role == "media":
        pack = role_packs.build_media_pack(root, week, season)
        contract = MEDIA_CONTRACT
    else:
        pack = role_packs.build_commissioner_pack(
            root, week, season, stage=stage or "waivers", window=window)
        contract = COMMISSIONER_CONTRACT[stage or "waivers"]

    system_text = "\n".join([
        persona(root, role),
        "",
        "---",
        "",
        "You are running as a one-shot turn. You have no tools and no file"
        " system: this runs in an empty directory with no repository checked"
        " out. Everything you are permitted to know is in the JSON below the"
        " contract. There is no path you can open, and nothing you write goes"
        " anywhere except the file the league office puts your reply in.",
        contract,
    ])
    user_text = "\n".join([
        f"Week {week} of the {season} season."
        + (f" Stage: {stage}." if stage else "")
        + (f" Window: {window}." if window else ""),
        "",
        "```json",
        json.dumps(pack, indent=1),
        "```",
    ])
    return system_text, user_text


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the media or commissioner turn as an isolated claude -p.")
    ap.add_argument("--role", choices=("media", "commissioner"), required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--stage", choices=("waivers", "lineups", "recap"),
                    help="commissioner only")
    ap.add_argument("--window", choices=("early", "main"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--save-raw", metavar="DIR")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and size the prompt, call nothing")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    if args.role == "commissioner" and not args.stage:
        ap.error("--stage is required for --role commissioner")
    if args.role == "commissioner" and args.stage == "lineups" and not args.window:
        args.window = "main"

    stage = args.stage if args.role == "commissioner" else None
    label = role_packs.WEEK_FILE.format(season=args.season, week=args.week)
    dest = root / OUTPUT_PATH[(args.role, stage)].format(
        label=label, window=args.window or "main")

    system_text, user_text = build(
        root, args.role, args.week, args.season, stage, args.window)

    who = args.role + (f"/{stage}" if stage else "")
    print(f"{who}: system {len(system_text):,} bytes + input "
          f"{len(user_text):,} bytes -> {dest.relative_to(root)}")

    if args.dry_run:
        return 0

    try:
        result = run_turn(
            system_text=system_text, user_text=user_text, model=args.model,
            timeout=args.timeout, label=who.replace("/", "-"),
            save_raw=pathlib.Path(args.save_raw) if args.save_raw else None)
    except TurnError as e:
        print(f"agent_turn: {e}", file=sys.stderr)
        return 1

    text = (result.text or "").strip()
    if not text:
        print("agent_turn: empty reply, nothing written", file=sys.stderr)
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text + "\n", encoding="utf-8")
    print(f"  wrote {dest.relative_to(root)} ({len(text):,} bytes) "
          f"on {args.model}")
    print(f"  {usage_line(dict(result.usage))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

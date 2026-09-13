#!/usr/bin/env python3
"""gm_turn.py — run the 12 GM turns as isolated `claude -p` calls.

    python scripts/gm_turn.py --week 2 --run waivers
    python scripts/gm_turn.py --week 2 --run lineups --window main
    python scripts/gm_turn.py --week 2 --run waivers --dry-run

Replaces the Grok Bot gateway dispatch (scripts/grok_bots.py dispatch) for the
GM step. Same packs, same schemas, same `state/weeks/*/decisions/<slug>.json`
output — only the transport changes, so faab.py, the commissioner gate and the
validators are untouched.

Why a subprocess per GM instead of subagents or one long chat:

  * Subagents get the repo. A GM that can Read the tree can open
    state/players.json or another team's opinions.json. Rejected.
  * One chat doing all 12 in sequence means GM 12 answers with GMs 1-11's
    reasoning and bids in its context. That is a parity break, and it quietly
    ends blind bidding.
  * A fresh `claude -p` per team is the only shape that is both isolated and
    cheap. Each turn runs with cwd set to an EMPTY temp directory, so isolation
    stops being a rule the model is asked to follow and becomes a property of
    the process: there are no files to read.

Token shape (measured, week 1):

  legacy  : 12 x ~97KB  = 1,166KB per waiver run (public record repeated 12x)
  this    : 1 x ~65KB shared + 12 x ~24KB private = ~357KB

The shared half goes in --append-system-prompt-file, byte-identical for all 12,
so it lands in the cached prefix. The first turn writes that cache and the other
eleven read it — which is why turn one is fired alone before the rest fan out.
Twelve simultaneous cold starts would each WRITE the cache instead.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import packs  # noqa: E402
from lib.claude_turn import (  # noqa: E402
    TurnError, accumulate, run_turn, usage_line,
)
from lib.decisions import load_schema, parse_and_validate  # noqa: E402
from lib.grok_dispatch import write_decision_file  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

DEFAULT_MODEL = "claude-sonnet-5"
# Parity rule 1: every GM gets the same model. Pinned rather than left to the
# CLI default so a default change upstream cannot silently split the field
# mid-season.

SCHEMA_FOR_RUN = {
    "waivers": "saturday-decision.json",
    "lineups": "sunday-lineup.json",
}


def turn_with_retry(slug: str, private_prompt: str, system_text: str,
                    schema: dict, *, model: str,
                    schema_arg: dict | None,
                    timeout: int,
                    save_raw: pathlib.Path | None = None) -> tuple:
    """Run a GM turn, retry once on a schema miss, then fall back.

    Matches the documented behaviour of the gateway path: retry once, and if it
    still will not validate, no claims this week with fallback: true — never a
    crashed run, never a hand-written decision.
    """
    last_errors = []
    usage = {}
    for attempt in (1, 2):
        try:
            result = run_turn(system_text=system_text, user_text=private_prompt,
                              model=model, schema=schema_arg, timeout=timeout,
                              label=slug, save_raw=save_raw)
        except TurnError as e:
            last_errors = [str(e)]
            continue
        usage = result.usage
        obj, errors = parse_and_validate(result.text, schema)
        if obj is not None and not errors:
            return obj, [], usage, attempt
        last_errors = errors or ["no JSON object in reply"]
    return None, last_errors, usage, 2


def fallback_object(run: str, slug: str, errors: list) -> dict:
    base = {"fallback": True, "team": slug,
            "fallback_reason": "; ".join(errors)[:300] or "unvalidated reply"}
    if run == "waivers":
        base.update({"claims": [], "drops": [], "note_reply": ""})
    else:
        base.update({"starters": {}, "bench": []})
    return base


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the 12 GM turns as isolated claude -p subprocesses.")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--run", choices=("waivers", "lineups"), default="waivers")
    ap.add_argument("--window", choices=("early", "main"), default=None)
    ap.add_argument("--team", help="one slug (default: all 12)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--concurrency", type=int, default=4,
                    help="parallel turns after the cache-warming first turn")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per turn")
    ap.add_argument("--no-structured", dest="structured", action="store_false",
                    help="do not pass --json-schema; validate the free-text "
                         "reply with the repo's own parser instead")
    ap.set_defaults(structured=True)
    ap.add_argument("--save-raw", metavar="DIR",
                    help="write each turn's raw claude envelope here (debugging)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and size the prompts, call nothing")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    if args.run == "lineups" and not args.window:
        args.window = "main"

    public = packs.build_public_pack(root, args.week, args.season)
    system_text = packs.build_gm_system(public, args.run, args.window)
    slugs = [args.team] if args.team else packs.team_slugs(root)

    prompts = {}
    for slug in slugs:
        private = packs.build_private_pack(
            root, slug, args.week, args.season, public=public,
            run=args.run, window=args.window, include_public=False)
        prompts[slug] = packs.render_private_prompt(private)

    shared = len(system_text)
    per_team = sum(len(v) for v in prompts.values())
    print(f"system (shared, cached after turn 1): {shared:,} bytes")
    print(f"private x{len(prompts)}:{'':>21} {per_team:,} bytes")
    print(f"on the wire:{'':>28} {shared + per_team:,} bytes")

    if args.dry_run:
        for slug, text in prompts.items():
            print(f"  {slug:<16} {len(text):>7,}")
        return 0

    schema_name = SCHEMA_FOR_RUN[args.run]
    schema = load_schema(schema_name)
    kind = "lineups" if args.run == "lineups" else "waivers"

    schema_arg = schema if args.structured else None

    started = time.time()
    results = {}

    def work(slug):
        return slug, turn_with_retry(
            slug, prompts[slug], system_text, schema,
            model=args.model, schema_arg=schema_arg, timeout=args.timeout,
            save_raw=pathlib.Path(args.save_raw) if args.save_raw else None)

    order = list(prompts)
    # Turn one alone: it writes the shared prefix into cache so the remaining
    # eleven read it. Firing all twelve cold would mean twelve cache writes.
    if order:
        results.update(dict([work(order[0])]))
        rest = order[1:]
        if rest:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=max(1, args.concurrency)) as pool:
                for slug, outcome in pool.map(work, rest):
                    results[slug] = outcome

    totals = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    failures = []
    for slug in order:
        obj, errors, usage, attempts = results[slug]
        accumulate(totals, usage)
        if obj is None:
            obj = fallback_object(args.run, slug, errors)
            failures.append(slug)
        dest = write_decision_file(
            root, season=args.season, week=args.week, slug=slug,
            kind=kind, obj=obj, window=args.window)
        flag = " FALLBACK" if obj.get("fallback") else ""
        retry = " (retried)" if attempts > 1 and not obj.get("fallback") else ""
        print(f"  {slug:<16} -> {dest.name}{retry}{flag}")

    elapsed = time.time() - started
    print(f"\n{len(order)} turns in {elapsed:,.0f}s on {args.model}")
    print(usage_line(totals))
    if failures:
        print(f"fallback (no moves logged): {', '.join(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

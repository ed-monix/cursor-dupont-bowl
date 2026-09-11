#!/usr/bin/env python3
"""grok_bots.py — roster, isolation check, paste prompts for Grok Bots.

    python scripts/grok_bots.py check
    python scripts/grok_bots.py list
    python scripts/grok_bots.py profile costanza
    python scripts/grok_bots.py prompt --week 1 --run waivers --slug costanza
    python scripts/grok_bots.py run-sheet --week 1 --run waivers

Does not create Bots (Grok Bot app). Does not clone the repo onto the
shared Bot computer. Owned teams (your-team, wifes-team) are Cursor-only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import grok_bots  # noqa: E402
from lib import packs  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def cmd_check(root: pathlib.Path) -> int:
    errors = grok_bots.check_roster(root)
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("OK: grok-bots roster isolation holds")
    return 0


def cmd_list(root: pathlib.Path) -> int:
    roster = grok_bots.load_roster(root)
    rows = []
    for role in grok_bots.roles(roster):
        rows.append({
            "id": role.get("id"),
            "kind": role.get("kind"),
            "bot_name": role.get("bot_name"),
            "product": role.get("product"),
            "computer": role.get("computer"),
            "off_shared_disk": bool(role.get("off_shared_disk")),
            "slug": role.get("slug"),
        })
    print(json.dumps({"isolation": roster.get("isolation"), "roles": rows}, indent=2))
    return 0


def _find_role(roster: dict, ident: str) -> dict:
    for role in grok_bots.roles(roster):
        if role.get("id") == ident or role.get("slug") == ident or role.get("bot_name") == ident:
            return role
    raise KeyError(f"no bot/role matching {ident!r}")


def cmd_profile(root: pathlib.Path, ident: str) -> int:
    roster = grok_bots.load_roster(root)
    role = _find_role(roster, ident)
    sys.stdout.write(grok_bots.profile_text(root, role))
    return 0


def cmd_prompt(root: pathlib.Path, week: int, run: str, slug: str,
               season: str, window: str | None) -> int:
    roster = grok_bots.load_roster(root)
    role = _find_role(roster, slug)
    if role.get("kind") != "gm":
        print("prompt is for GM roles; use bots/skill-*.md for scout/media/commish",
              file=sys.stderr)
        return 1
    team = role["slug"]
    if run == "lineups" and not window:
        window = "main"
    public = packs.build_public_pack(root, week, season)
    private = packs.build_private_pack(
        root, team, week, season, public=public, run=run, window=window,
    )
    text = packs.render_gm_prompt(private)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def cmd_run_sheet(root: pathlib.Path, week: int, run: str, season: str,
                  window: str | None) -> int:
    roster = grok_bots.load_roster(root)
    errors = grok_bots.check_roster(root, roster)
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    win = f" --window {window}" if run == "lineups" and window else ""
    print(f"# DuPont Bowl {run} week {week:02d}")
    print("# Do NOT git-clone this repo onto the Grok Bot computer.")
    print("# Paste each prompt into that Bot. Tools off. Save JSON to decisions/.")
    print()
    for role in grok_bots.roles(roster):
        kind = role["kind"]
        name = role["bot_name"]
        product = role["product"]
        print(f"## {name} ({kind}, {product})")
        if kind == "scout":
            print("  skill: bots/skill-scout.md")
            print("  write: state/news/buzz/YYYY-wNN.md (owner paste wins)")
        elif kind == "media":
            print("  skill: bots/skill-media.md + agents/media.md in chat")
            print("  write: state/news/YYYY-wNN.md")
        elif kind == "commissioner":
            print("  skill: bots/skill-commish.md")
            print("  GM files in chat only; scripts apply FAAB/lineups")
        elif kind == "gm":
            slug = role["slug"]
            disk = "OFF shared disk" if role.get("off_shared_disk") else "shared Bot"
            print(f"  slug: {slug}  [{disk}]")
            print(
                f"  python scripts/grok_bots.py prompt --week {week} "
                f"--run {run} --slug {slug}{win}"
            )
            if run == "lineups":
                out = f"state/weeks/{season}-w{week:02d}/decisions/{slug}.lineup-{window or 'main'}.json"
            else:
                out = f"state/weeks/{season}-w{week:02d}/decisions/{slug}.json"
            print(f"  save reply -> {out}")
        print()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Grok Bot roster and pack prompts")
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check")
    sub.add_parser("list")
    p_prof = sub.add_parser("profile")
    p_prof.add_argument("id")
    p_pr = sub.add_parser("prompt")
    p_pr.add_argument("--week", type=int, required=True)
    p_pr.add_argument("--run", choices=("waivers", "lineups"), required=True)
    p_pr.add_argument("--slug", required=True)
    p_pr.add_argument("--season", default="2026")
    p_pr.add_argument("--window", choices=("early", "main"))
    p_sheet = sub.add_parser("run-sheet")
    p_sheet.add_argument("--week", type=int, required=True)
    p_sheet.add_argument("--run", choices=("waivers", "lineups"), required=True)
    p_sheet.add_argument("--season", default="2026")
    p_sheet.add_argument("--window", choices=("early", "main"))

    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.cmd == "check":
        return cmd_check(root)
    if args.cmd == "list":
        return cmd_list(root)
    if args.cmd == "profile":
        return cmd_profile(root, args.id)
    if args.cmd == "prompt":
        return cmd_prompt(root, args.week, args.run, args.slug, args.season, args.window)
    if args.cmd == "run-sheet":
        return cmd_run_sheet(root, args.week, args.run, args.season, args.window)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

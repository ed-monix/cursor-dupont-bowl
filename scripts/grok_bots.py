#!/usr/bin/env python3
"""grok_bots.py — roster, isolation check, gateway dispatch.

    python scripts/grok_bots.py check
    python scripts/grok_bots.py list
    python scripts/grok_bots.py profile costanza
    python scripts/grok_bots.py ensure
    python scripts/grok_bots.py dispatch --week 1 --kind waivers
    python scripts/grok_bots.py prompt --week 1 --run waivers --slug costanza
    python scripts/grok_bots.py run-sheet --week 1 --run waivers

Weekly clock is dispatch (gateway sendPrompt), not pasting 12 chats.
Does not clone the repo onto the shared Bot computer. Owned teams
(your-team, wifes-team) stay Cursor-only and are never dispatched.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import grok_bots  # noqa: E402
from lib import grok_dispatch  # noqa: E402
from lib import packs  # noqa: E402
from lib.grok_gateway import (  # noqa: E402
    GatewayError,
    enablement_text,
    list_agents,
    load_gateway_config,
)

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
            "gateway_agent_id": role.get("gateway_agent_id"),
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
    print("# Weekly clock: dispatch. Do not paste 12 packs by hand.")
    print("# Do NOT git-clone this repo onto the Grok Bot computer.")
    print()
    print(
        f"python scripts/grok_bots.py dispatch --week {week} "
        f"--kind {run}{win}"
    )
    print("# then scripts apply: faab.py / lineups.py")
    print("# owned GMs (your-team, wifes-team): Cursor pack-only, not dispatched")
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
            if product == "cursor":
                print(
                    f"  python scripts/grok_bots.py prompt --week {week} "
                    f"--run {run} --slug {slug}{win}"
                )
            else:
                gid = role.get("gateway_agent_id") or "(run ensure)"
                print(f"  gateway_agent_id: {gid}")
                print(
                    f"  python scripts/grok_bots.py dispatch --week {week} "
                    f"--kind {run} --slug {slug}{win}"
                )
            if run == "lineups":
                out = (
                    f"state/weeks/{season}-w{week:02d}/decisions/"
                    f"{slug}.lineup-{window or 'main'}.json"
                )
            else:
                out = f"state/weeks/{season}-w{week:02d}/decisions/{slug}.json"
            print(f"  save reply -> {out}")
        print()
    return 0


def _need_gateway():
    try:
        cfg = load_gateway_config()
    except GatewayError as e:
        print(str(e), file=sys.stderr)
        print(enablement_text(), file=sys.stderr)
        return None
    if cfg is None:
        print(enablement_text(), file=sys.stderr)
        return None
    return cfg


def cmd_gateway(root: pathlib.Path) -> int:
    cfg = _need_gateway()
    if cfg is None:
        return 2
    try:
        agents = list_agents(cfg)
    except GatewayError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"source": cfg.source, "base_url": cfg.base_url, "agents": len(agents)}, indent=2))
    return 0


def cmd_ensure(root: pathlib.Path, dry_run: bool) -> int:
    cfg = _need_gateway()
    if cfg is None:
        return 2
    roster = grok_bots.load_roster(root)
    errors = grok_bots.check_roster(root, roster)
    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    try:
        roster, notes = grok_dispatch.ensure_agents(cfg, roster, root=root)
    except GatewayError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    for note in notes:
        print(note)
    if dry_run:
        print("dry-run: roster not written")
        return 0
    grok_bots.write_roster(root, roster)
    print(f"wrote {grok_bots.config_path(root)}")
    return 0


def cmd_dispatch(
    root: pathlib.Path,
    week: int,
    kind: str,
    season: str,
    window: str | None,
    slugs: list[str] | None,
    offer_path: str | None,
    dry_run: bool,
) -> int:
    if kind == "lineups" and not window:
        window = "main"
    if kind == "trades" and not slugs:
        print("trades dispatch requires --slug <target>", file=sys.stderr)
        return 2
    offer = None
    if offer_path:
        offer = json.loads(pathlib.Path(offer_path).read_text(encoding="utf-8"))
    cfg = _need_gateway()
    if cfg is None:
        return 2
    results = grok_dispatch.dispatch_week(
        cfg,
        week=week,
        kind=kind,
        root=root,
        slugs=slugs,
        window=window,
        offer=offer,
        season=season,
        dry_run=dry_run,
    )
    failed = 0
    for row in results:
        if row.skipped:
            print(f"DRY {row.slug}")
            continue
        if row.ok:
            print(f"OK  {row.slug} -> {row.path}")
        else:
            failed += 1
            print(f"FAIL {row.slug}: {row.error}", file=sys.stderr)
    return 1 if failed else 0


def cmd_routines(root: pathlib.Path, ident: str | None) -> int:
    from lib import routines
    sys.stdout.write(routines.render_catalog(root, ident))
    return 0


def cmd_ops(root: pathlib.Path, day: str | None, season: str) -> int:
    from datetime import date
    from lib.daily_ops import ops_for_root
    today = date.fromisoformat(day) if day else date.today()
    json.dump(ops_for_root(root, today=today, season=season), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Grok Bot roster, commissioner clock, and dispatch"
    )
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check")
    sub.add_parser("list")
    sub.add_parser("gateway")
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
    p_ens = sub.add_parser("ensure")
    p_ens.add_argument("--dry-run", action="store_true")
    p_disp = sub.add_parser("dispatch")
    p_disp.add_argument("--week", type=int, required=True)
    p_disp.add_argument("--kind", choices=("waivers", "lineups", "trades"), required=True)
    p_disp.add_argument("--season", default="2026")
    p_disp.add_argument("--window", choices=("early", "main"))
    p_disp.add_argument("--slug", action="append", dest="slugs")
    p_disp.add_argument("--offer", help="trade-offer JSON file (kind=trades)")
    p_disp.add_argument("--dry-run", action="store_true")
    p_rt = sub.add_parser("routines")
    p_rt.add_argument("id", nargs="?", help="gm|commissioner|daily-slate|on-commissioner")
    p_ops = sub.add_parser("ops")
    p_ops.add_argument("--date", help="YYYY-MM-DD")
    p_ops.add_argument("--season", default="2026")

    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.cmd == "check":
        return cmd_check(root)
    if args.cmd == "list":
        return cmd_list(root)
    if args.cmd == "gateway":
        return cmd_gateway(root)
    if args.cmd == "profile":
        return cmd_profile(root, args.id)
    if args.cmd == "prompt":
        return cmd_prompt(root, args.week, args.run, args.slug, args.season, args.window)
    if args.cmd == "run-sheet":
        return cmd_run_sheet(root, args.week, args.run, args.season, args.window)
    if args.cmd == "ensure":
        return cmd_ensure(root, args.dry_run)
    if args.cmd == "dispatch":
        return cmd_dispatch(
            root,
            args.week,
            args.kind,
            args.season,
            args.window,
            args.slugs,
            args.offer,
            args.dry_run,
        )
    if args.cmd == "routines":
        return cmd_routines(root, args.id)
    if args.cmd == "ops":
        return cmd_ops(root, args.date, args.season)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

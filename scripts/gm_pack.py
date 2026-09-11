#!/usr/bin/env python3
"""gm_pack.py — write the week's public + per-team private GM packs.

    python scripts/gm_pack.py --week 2
    python scripts/gm_pack.py --week 2 --team your-team --run lineups --window early --prompt

The fat files (players.json, full free-agents.json, projections) stay on
disk for the engine. GMs get the pack (or --prompt stdout) and must not
Read the tree. Isolation: --team only ever opens teams/<that-slug>/.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import packs  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _week_dir(root: pathlib.Path, season: str, week: int) -> pathlib.Path:
    path = root / "state" / "weeks" / f"{season}-w{week:02d}" / "packs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build dieted GM packs for a week")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--season", default="2026")
    ap.add_argument("--team", help="one slug; default: every team")
    ap.add_argument("--run", choices=("waivers", "lineups"), default="waivers")
    ap.add_argument("--window", choices=("early", "main"), default=None)
    ap.add_argument("--prompt", action="store_true",
                    help="print the inline GM prompt for --team (no extra files)")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()
    root = pathlib.Path(args.root)

    if args.run == "lineups" and not args.window:
        args.window = "main"

    public = packs.build_public_pack(root, args.week, args.season)
    out_dir = _week_dir(root, args.season, args.week)
    public_path = out_dir / "public.json"
    public_path.write_text(json.dumps(public, indent=1) + "\n", encoding="utf-8")

    slugs = [args.team] if args.team else packs.team_slugs(root)
    sizes = []
    for slug in slugs:
        private = packs.build_private_pack(
            root, slug, args.week, args.season,
            public=public, run=args.run, window=args.window,
        )
        dest = out_dir / f"{slug}.json"
        dest.write_text(json.dumps(private, indent=1) + "\n", encoding="utf-8")
        sz = packs.pack_sizes(public, private)
        sz["team"] = slug
        sizes.append(sz)
        if args.prompt and args.team == slug:
            text = packs.render_gm_prompt(private)
            sys.stdout.write(text if text.endswith("\n") else text + "\n")

    summary = {
        "public": str(public_path),
        "public_bytes": len(json.dumps(public).encode("utf-8")),
        "fa_full": public.get("free_agents_full_count"),
        "fa_trimmed": public.get("free_agents_trimmed_count"),
        "teams": sizes,
    }
    (out_dir / "sizes.json").write_text(json.dumps(summary, indent=1) + "\n")
    if not args.prompt:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n# pack sizes: {json.dumps(summary)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Grok Bot routine catalog (cloud webhooks, not a Mac)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from lib import packs


def routines_path(root: Union[str, Path]) -> Path:
    return Path(root) / "config" / "routines.json"


def load_routines(root: Union[str, Path]) -> dict:
    data = json.loads(routines_path(root).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("routines"), list):
        raise ValueError(f"{routines_path(root)} must have a routines array")
    return data


def gameday_note_filename(season: str, week: int, window: str) -> str:
    return f"{season}-w{week:02d}-{window}.md"


def webhook_envelope(
    *,
    week: int,
    kind: str,
    slug: str,
    prompt: str,
    window: Optional[str] = None,
    season: str = "2026",
) -> dict[str, Any]:
    return {
        "league": "dupont-bowl",
        "season": season,
        "week": week,
        "kind": kind,
        "window": window,
        "slug": slug,
        "prompt": prompt,
    }


def pack_webhook_envelope(
    root: Union[str, Path],
    *,
    week: int,
    kind: str,
    slug: str,
    window: Optional[str] = None,
    season: str = "2026",
) -> dict[str, Any]:
    pack_run = "waivers" if kind in ("waivers", "trades") else "lineups"
    if pack_run == "lineups" and not window:
        window = "main"
    public = packs.build_public_pack(root, week, season)
    private = packs.build_private_pack(
        root, slug, week, season, public=public, run=pack_run, window=window,
    )
    prompt = packs.render_gm_prompt(private)
    return webhook_envelope(
        week=week, kind=kind, slug=slug, prompt=prompt, window=window, season=season,
    )


def render_catalog(root: Union[str, Path], ident: Optional[str] = None) -> str:
    data = load_routines(root)
    lines = [
        f"# DuPont Bowl routines ({data.get('timezone')})",
        data.get("clock") or "",
        "",
    ]
    for row in data["routines"]:
        if ident and row.get("id") != ident and ident not in (row.get("roles") or []):
            continue
        lines.append(f"## {row.get('id')}")
        lines.append(f"roles: {', '.join(row.get('roles') or [])}")
        lines.append(f"trigger: {row.get('trigger')}")
        if row.get("schedule"):
            lines.append(
                f"backup cron ({data.get('timezone')}): {row['schedule']}"
                + (f" — {row['schedule_note']}" if row.get("schedule_note") else "")
            )
        if row.get("notes"):
            lines.append("picks up pack fields: " + ", ".join(row["notes"]))
        if row.get("skill"):
            lines.append(f"instructions: {row['skill']}")
        lines.append("")
    overview = Path(root) / "bots" / "routines.md"
    if ident in (None, "commissioner", "daily-slate") and overview.is_file():
        lines.append(overview.read_text(encoding="utf-8"))
    gm = Path(root) / "bots" / "routines-gm.md"
    if ident in (None, "gm", "on-commissioner") and gm.is_file():
        lines.append(gm.read_text(encoding="utf-8"))
    other = Path(root) / "bots" / "routines-other.md"
    if ident in (None, "scout", "media", "on-commissioner-scout", "on-commissioner-media") and other.is_file():
        lines.append(other.read_text(encoding="utf-8"))
    return "\n".join(lines).rstrip() + "\n"

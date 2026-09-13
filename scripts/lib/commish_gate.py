"""Commissioner gate: validate GM replies, then a Cloud Agent writes git.

GMs report to the Commissioner only. Invalid JSON never lands in git.
Gate / daily ops: Cloud Agent commits and pushes straight to main.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from lib.daily_ops import ops_dir, write_ops
from lib.decisions import load_schema, parse_and_validate
from lib.grok_dispatch import KIND_LINEUPS, KIND_TRADES, KIND_WAIVERS, write_decision_file

KIND_MAP = {
    "waivers": KIND_WAIVERS,
    "lineups": KIND_LINEUPS,
    "lineups-early": KIND_LINEUPS,
    "lineups-main": KIND_LINEUPS,
    "trades": KIND_TRADES,
    "trade": KIND_TRADES,
}


def schema_for(kind: str) -> dict:
    mapped = KIND_MAP.get(kind, kind)
    if mapped == KIND_LINEUPS:
        return load_schema("sunday-lineup.json")
    if mapped == KIND_TRADES:
        return load_schema("trade-response.json")
    return load_schema("saturday-decision.json")


def normalize_kind_window(kind: str, window: Optional[str]) -> tuple[str, Optional[str]]:
    if kind == "lineups-early":
        return KIND_LINEUPS, "early"
    if kind == "lineups-main":
        return KIND_LINEUPS, "main"
    mapped = KIND_MAP.get(kind, kind)
    if mapped == KIND_LINEUPS and not window:
        window = "main"
    return mapped, window


def ingest_reply(
    root: Union[str, Path],
    *,
    raw: str,
    slug: str,
    kind: str,
    week: int,
    window: Optional[str] = None,
    season: str = "2026",
    ops_day: Optional[str] = None,
) -> dict:
    """Validate one GM reply. Write decisions/ only if it passes."""
    root = Path(root)
    mapped, window = normalize_kind_window(kind, window)
    obj, errors = parse_and_validate(raw, schema_for(kind if kind in KIND_MAP else mapped))
    record = {
        "ok": not errors,
        "slug": slug,
        "kind": mapped,
        "window": window,
        "errors": errors,
        "path": None,
    }
    if errors:
        _update_ops_gate(root, ops_day, slug, ok=False, detail="; ".join(errors))
        return record
    dest = write_decision_file(
        root,
        season=season,
        week=week,
        slug=slug,
        kind=mapped,
        obj=obj,
        window=window,
    )
    record["path"] = str(dest)
    _update_ops_gate(root, ops_day, slug, ok=True, detail=str(dest))
    return record


def _update_ops_gate(
    root: Path,
    ops_day: Optional[str],
    slug: str,
    *,
    ok: bool,
    detail: str,
) -> None:
    folder = ops_dir(root)
    latest = folder / "latest.json"
    path = folder / f"{ops_day}.json" if ops_day else latest
    if not path.is_file():
        if latest.is_file():
            path = latest
        else:
            return
    data = json.loads(path.read_text(encoding="utf-8"))
    gate = data.setdefault("gate", {"received": {}, "rejected": {}})
    if ok:
        gate.setdefault("received", {})[slug] = detail
        gate.get("rejected", {}).pop(slug, None)
    else:
        gate.setdefault("rejected", {})[slug] = detail
    write_ops(root, data)

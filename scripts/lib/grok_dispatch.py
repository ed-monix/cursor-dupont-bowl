"""Dispatch weekly packs to Grok Bots via the desktop gateway.

The weekly clock is this repo — one command, not Nick pasting 12 chats.
Packs are built in memory and POSTed as prompt text. GM files are never
copied onto the shared Bot computer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

from lib.decisions import load_schema, parse_and_validate
from lib import grok_bots
from lib.grok_gateway import (
    GatewayConfig,
    GatewayError,
    agent_id_of,
    create_agent,
    extract_reply_text,
    find_agent,
    list_agents,
    send_prompt,
    wait_until_idle,
)
from lib import packs

KIND_WAIVERS = "waivers"
KIND_LINEUPS = "lineups"
KIND_TRADES = "trades"
DISPATCH_KINDS = (KIND_WAIVERS, KIND_LINEUPS, KIND_TRADES)

OWNED = frozenset(grok_bots.OWNED_SLUGS)


@dataclass(frozen=True)
class DispatchResult:
    slug: str
    ok: bool
    path: Optional[str]
    error: Optional[str]
    skipped: bool = False


def celebrity_gm_roles(roster: dict) -> list:
    out = []
    for role in grok_bots.gm_roles(roster):
        if role.get("product") != "grok_bot":
            continue
        slug = role.get("slug")
        if not slug or slug in OWNED:
            continue
        out.append(role)
    return out


def skill_relpath(role: dict) -> str:
    if role.get("skill"):
        return str(role["skill"])
    kind = role.get("kind")
    if kind == "gm":
        return "bots/skill-gm.md"
    if kind == "scout":
        return "bots/skill-scout.md"
    if kind == "media":
        return "bots/skill-media.md"
    if kind == "commissioner":
        return "bots/skill-commish.md"
    raise ValueError(f"no skill for role {role.get('id')}")


def skill_text(root: Union[str, Path], role: dict) -> str:
    path = Path(root) / skill_relpath(role)
    return path.read_text(encoding="utf-8")


def create_instructions(root: Union[str, Path], role: dict) -> str:
    profile = grok_bots.profile_text(root, role).strip()
    skill = skill_text(root, role).strip()
    extra = (
        "You are the git gate. Clone this repo. Ingest GM JSON. Commit."
        if role.get("kind") == "commissioner"
        else "Do not clone git. Reply JSON to the Commissioner only."
    )
    return (
        f"{profile}\n\n---\n{skill}\n\n{extra}\n"
    )


def ensure_agents(
    cfg: GatewayConfig,
    roster: dict,
    *,
    root: Union[str, Path],
    create: Callable[..., dict[str, Any]] = create_agent,
    list_fn: Callable[[GatewayConfig], list] = list_agents,
) -> tuple[dict, list[str]]:
    """Create or link missing Bots; stamp gateway_agent_id on roster roles."""
    notes: list[str] = []
    agents = list_fn(cfg)
    root = Path(root)
    for role in roster.get("roles") or []:
        if role.get("product") != "grok_bot":
            continue
        if role.get("gateway_agent_id"):
            continue
        name = role.get("bot_name") or role.get("id")
        existing = find_agent(agents, name=str(name))
        if existing is not None:
            role["gateway_agent_id"] = agent_id_of(existing)
            notes.append(f"linked {role.get('id')} -> {role['gateway_agent_id']}")
            continue
        created = create(
            cfg,
            name=str(name),
            instructions=create_instructions(root, role),
            model=role.get("model") or None,
        )
        new_id = _id_from_create(created)
        if not new_id:
            agents = list_fn(cfg)
            found = find_agent(agents, name=str(name))
            if found is None:
                raise GatewayError(f"createAgent did not return an id for {name}")
            new_id = agent_id_of(found)
        role["gateway_agent_id"] = new_id
        notes.append(f"created {role.get('id')} -> {new_id}")
    return roster, notes


def _id_from_create(created: Any) -> Optional[str]:
    if not isinstance(created, dict):
        return None
    try:
        return agent_id_of(created)
    except GatewayError:
        nested = created.get("agent") or created.get("data")
        if isinstance(nested, dict):
            try:
                return agent_id_of(nested)
            except GatewayError:
                return None
    return None


def decision_filename(slug: str, kind: str, window: Optional[str] = None) -> str:
    if kind == KIND_LINEUPS:
        return f"{slug}.lineup-{window or 'main'}.json"
    if kind == KIND_TRADES:
        return f"{slug}.trade.json"
    return f"{slug}.json"


def write_decision_file(
    out_root: Path,
    *,
    season: str,
    week: int,
    slug: str,
    kind: str,
    obj: dict,
    window: Optional[str] = None,
) -> Path:
    dest_dir = out_root / "state" / "weeks" / f"{season}-w{week:02d}" / "decisions"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / decision_filename(slug, kind, window)
    dest.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return dest


def _schema_for_kind(kind: str) -> dict:
    if kind == KIND_LINEUPS:
        return load_schema("sunday-lineup.json")
    if kind == KIND_TRADES:
        return load_schema("trade-response.json")
    return load_schema("saturday-decision.json")


def _prompt_for_kind(
    kind: str,
    pack_md: str,
    *,
    window: Optional[str] = None,
    offer: Optional[dict] = None,
) -> str:
    if kind == KIND_LINEUPS:
        extra = (
            f"This is lineup window `{window or 'main'}`. "
            "Return ONLY the JSON object matching docs/schemas/sunday-lineup.json. "
            "No markdown fences, no prose."
        )
    elif kind == KIND_TRADES:
        offer_json = json.dumps(offer or {}, indent=2)
        extra = (
            "A trade offer addressed to you is below. Scripts already checked "
            "it is legal. Return ONLY JSON matching docs/schemas/trade-response.json "
            "(accept, reject, or counter). No markdown fences, no prose.\n\n"
            f"```json\n{offer_json}\n```"
        )
    else:
        extra = (
            "Return ONLY the JSON object matching docs/schemas/saturday-decision.json. "
            "Empty claims array if you want nobody. No markdown fences, no prose."
        )
    return (
        f"{pack_md}\n\n---\n{extra}\n"
        "Do not clone any git repo. Do not write files. Reply with JSON only.\n"
    )


def dispatch_one(
    cfg: GatewayConfig,
    *,
    week: int,
    kind: str,
    role: dict,
    agent_id: str,
    pack_root: Path,
    out_root: Path,
    season: str = "2026",
    window: Optional[str] = None,
    offer: Optional[dict] = None,
    public: Optional[dict] = None,
    send: Callable[..., Any] = send_prompt,
    wait: Callable[..., dict] = wait_until_idle,
    extract: Callable[..., str] = extract_reply_text,
    dry_run: bool = False,
) -> DispatchResult:
    slug = role["slug"]
    if kind not in DISPATCH_KINDS:
        return DispatchResult(slug, False, None, f"unknown kind {kind}")
    pack_run = KIND_WAIVERS if kind == KIND_TRADES else kind
    pack = packs.build_private_pack(
        pack_root,
        slug,
        week,
        season,
        public=public,
        run=pack_run,
        window=window if pack_run == KIND_LINEUPS else None,
    )
    pack_md = packs.render_gm_prompt(pack)
    prompt = _prompt_for_kind(kind, pack_md, window=window, offer=offer)
    if dry_run:
        return DispatchResult(slug, True, None, None, skipped=True)

    payload = send(cfg, agent_id=agent_id, prompt=prompt)
    try:
        text = extract(payload)
    except GatewayError:
        agent = wait(cfg, agent_id=agent_id)
        text = extract(payload, agent)

    obj, errors = parse_and_validate(text, _schema_for_kind(kind))
    if errors:
        return DispatchResult(slug, False, None, "; ".join(errors))
    dest = write_decision_file(
        out_root,
        season=season,
        week=week,
        slug=slug,
        kind=kind,
        obj=obj,
        window=window,
    )
    return DispatchResult(slug, True, str(dest), None)


def dispatch_week(
    cfg: GatewayConfig,
    *,
    week: int,
    kind: str,
    root: Path,
    out_root: Optional[Path] = None,
    slugs: Optional[list[str]] = None,
    window: Optional[str] = None,
    offer: Optional[dict] = None,
    season: str = "2026",
    dry_run: bool = False,
) -> list[DispatchResult]:
    out_root = out_root or root
    roster = grok_bots.load_roster(root)
    celebrity = celebrity_gm_roles(roster)
    if slugs:
        extra = [s for s in slugs if s not in {r.get("slug") for r in celebrity}]
        rows = [r for r in celebrity if r.get("slug") in set(slugs)]
        results: list[DispatchResult] = [
            DispatchResult(s, False, None, "not a celebrity grok_bot GM")
            for s in extra
        ]
    else:
        rows = celebrity
        results = []

    public = packs.build_public_pack(root, week, season)
    for role in rows:
        slug = role["slug"]
        agent_id = str(role.get("gateway_agent_id") or "")
        if not agent_id:
            results.append(
                DispatchResult(
                    slug,
                    False,
                    None,
                    "no gateway_agent_id — run: python scripts/grok_bots.py ensure",
                )
            )
            continue
        try:
            results.append(
                dispatch_one(
                    cfg,
                    week=week,
                    kind=kind,
                    role=role,
                    agent_id=agent_id,
                    pack_root=root,
                    out_root=out_root,
                    season=season,
                    window=window,
                    offer=offer,
                    public=public,
                    dry_run=dry_run,
                )
            )
        except (GatewayError, ValueError, OSError) as e:
            results.append(DispatchResult(slug, False, None, str(e)))
    return results

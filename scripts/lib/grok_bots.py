"""Grok Bot roster + isolation checks (config/grok-bots.json).

Grok Bots on one xAI account share one computer. Creation can go through
the Grok Bot app or `grok_bots.py ensure` via the local gateway. Isolation
is pack-in-chat (tools off), not files on the shared disk.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

OWNED_SLUGS = ("your-team", "wifes-team")
KINDS = ("scout", "media", "commissioner", "gm")
PRODUCTS = ("grok_bot", "cursor")
COMPUTERS = ("shared", "none")


def config_path(root: Union[str, Path]) -> Path:
    return Path(root) / "config" / "grok-bots.json"


def load_roster(root: Union[str, Path]) -> dict:
    path = config_path(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("roles"), list):
        raise ValueError(f"{path} must have a roles array")
    return data


def write_roster(root: Union[str, Path], roster: dict) -> Path:
    path = config_path(root)
    path.write_text(json.dumps(roster, indent=2) + "\n", encoding="utf-8")
    return path


def roles(roster: dict, kind: Optional[str] = None) -> list:
    out = []
    for role in roster.get("roles") or []:
        if not isinstance(role, dict):
            continue
        if kind and role.get("kind") != kind:
            continue
        out.append(role)
    return out


def gm_roles(roster: dict) -> list:
    return roles(roster, "gm")


def shared_disk_roles(roster: dict) -> list:
    return [r for r in roles(roster) if r.get("computer") == "shared"]


def off_disk_slugs(roster: dict) -> list:
    iso = roster.get("isolation") or {}
    listed = list(iso.get("owned_teams_off_disk") or [])
    for role in gm_roles(roster):
        if role.get("off_shared_disk") and role.get("slug"):
            if role["slug"] not in listed:
                listed.append(role["slug"])
    return listed


def team_slugs_on_disk(root: Union[str, Path]) -> list:
    teams = Path(root) / "teams"
    slugs = []
    if not teams.is_dir():
        return slugs
    for child in sorted(teams.iterdir()):
        if child.name.startswith("_"):
            continue
        if (child / "general-manager.md").exists() or (child / "roster.json").exists():
            slugs.append(child.name)
    return slugs


def check_roster(root: Union[str, Path], roster: Optional[dict] = None) -> list:
    """Return human-readable errors. Empty list = legal roster."""
    root = Path(root)
    roster = roster if roster is not None else load_roster(root)
    errors = []
    seen_ids = set()
    gm_slugs = []

    iso = roster.get("isolation") or {}
    owned = list(iso.get("owned_teams_off_disk") or [])
    for slug in OWNED_SLUGS:
        if slug not in owned:
            errors.append(f"isolation.owned_teams_off_disk missing {slug}")

    for role in roles(roster):
        rid = role.get("id")
        kind = role.get("kind")
        if not rid:
            errors.append("role missing id")
            continue
        if rid in seen_ids:
            errors.append(f"duplicate role id {rid}")
        seen_ids.add(rid)
        if kind not in KINDS:
            errors.append(f"{rid}: unknown kind {kind!r}")
        if role.get("product") not in PRODUCTS:
            errors.append(f"{rid}: unknown product {role.get('product')!r}")
        if role.get("computer") not in COMPUTERS:
            errors.append(f"{rid}: unknown computer {role.get('computer')!r}")
        if role.get("mount_repo"):
            errors.append(f"{rid}: mount_repo is forbidden")
        if kind in ("scout", "media") and not role.get("never_read_gm_files"):
            errors.append(f"{rid}: {kind} must set never_read_gm_files")
        if kind == "gm":
            slug = role.get("slug")
            if not slug:
                errors.append(f"{rid}: GM role missing slug")
            else:
                gm_slugs.append(slug)
            if not role.get("own_gm_file_in_pack_only"):
                errors.append(f"{rid}: GM personality must travel in the pack only")
            if slug in OWNED_SLUGS:
                if not role.get("off_shared_disk"):
                    errors.append(f"{rid}: owned GM must set off_shared_disk")
                if role.get("computer") == "shared":
                    errors.append(f"{rid}: owned GM must not use the shared Bot computer")
                if role.get("product") == "grok_bot":
                    errors.append(
                        f"{rid}: owned GM stays off Grok Bot this trial (product=cursor)"
                    )
            elif role.get("computer") == "shared" and role.get("off_shared_disk"):
                errors.append(f"{rid}: celebrity GM on shared disk cannot be off_shared_disk")

    expected = team_slugs_on_disk(root)
    missing = sorted(set(expected) - set(gm_slugs))
    extra = sorted(set(gm_slugs) - set(expected))
    if missing:
        errors.append(f"roster missing team slugs: {missing}")
    if extra:
        errors.append(f"roster has unknown team slugs: {extra}")
    return errors


def public_bio(root: Union[str, Path], slug: str) -> str:
    path = Path(root) / "teams" / slug / "general-manager.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    capturing = False
    bio = []
    for line in lines:
        if line.strip() == "## Public bio":
            capturing = True
            continue
        if capturing:
            if line.startswith("## "):
                break
            bio.append(line)
    return "\n".join(bio).strip()


def profile_text(root: Union[str, Path], role: dict) -> str:
    """Grok Bot Edit Profile body: job + isolation. Not the full GM file."""
    kind = role.get("kind")
    name = role.get("bot_name") or role.get("id")
    lines = [
        f"Name: {name}",
        f"Job: DuPont Bowl {kind}.",
    ]
    if kind == "gm":
        lines.append(f"Character: {role.get('character') or role.get('slug')}.")
        bio = public_bio(root, role.get("slug") or "")
        if bio:
            lines.append("")
            lines.append("Public bio (league-facing, not a secret file):")
            lines.append(bio)
        lines.append("")
        lines.append(
            "The Commissioner wakes you. You have no personal calendar. "
            "Each turn you receive ONE pack in the chat. Tools off. Do not read "
            "files, clone git, or search X. Reply with schema JSON only. Your "
            "full GM instructions arrive inside that pack (general_manager_md). "
            "On gameday read owner_note and gameday_note (pressure, not orders). "
            "Do not keep other teams' files. Do not ask for players.json."
        )
    elif kind == "media":
        lines.append(
            "You are Kris Jenner. Public record only. Never open a GM file or "
            "opinions.json. Rewrite news-facts + optional buzz into the tabloid."
        )
    elif kind == "commissioner":
        lines.append(
            "You are the daily clock: 09:00 America/New_York, public NFL slate "
            "only (daily_ops.py). Wake other Bots; do not clone git; do not "
            "attach GM files to a wake. Review is separate: block illegal only. "
            "Chaos is legal. Do not apply FAAB. GM files only in review chat, "
            "never left on the shared disk."
        )
    elif kind == "scout":
        lines.append(
            "One measured X pass per week into buzz markdown. Sentiment only. "
            "Never invent post counts. Never read GM files."
        )
    lines.append("")
    lines.append(
        "Shared computer: other Bots can see anything you save to disk. "
        "Do not write GM files, opinions.json, players.json, or buzz drafts "
        "to the computer. Packs arrive in chat only."
    )
    return "\n".join(lines) + "\n"

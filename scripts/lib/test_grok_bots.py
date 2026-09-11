"""Tests for config/grok-bots.json isolation."""
from __future__ import annotations

from pathlib import Path

import grok_bots as grok_bots_cli
from lib import grok_bots

REPO = Path(__file__).resolve().parents[2]


def test_committed_roster_passes_check():
    assert grok_bots.check_roster(REPO) == []


def test_owned_teams_are_not_on_shared_computer():
    roster = grok_bots.load_roster(REPO)
    assert grok_bots.off_disk_slugs(roster) == ["your-team", "wifes-team"]
    for role in grok_bots.gm_roles(roster):
        if role["slug"] in grok_bots.OWNED_SLUGS:
            assert role["off_shared_disk"] is True
            assert role["computer"] == "none"
            assert role["product"] == "cursor"
        else:
            assert role["computer"] == "shared"
            assert role["product"] == "grok_bot"
            assert role["own_gm_file_in_pack_only"] is True


def test_media_and_scout_never_read_gm_files():
    roster = grok_bots.load_roster(REPO)
    for role in grok_bots.roles(roster):
        if role["kind"] in ("media", "scout"):
            assert role["never_read_gm_files"] is True


def test_check_rejects_owned_gm_on_shared_disk():
    roster = grok_bots.load_roster(REPO)
    for role in roster["roles"]:
        if role.get("slug") == "your-team":
            role["computer"] = "shared"
            role["off_shared_disk"] = False
            role["product"] = "grok_bot"
    errors = grok_bots.check_roster(REPO, roster)
    assert any("owned GM" in e or "shared" in e for e in errors)


def test_check_rejects_missing_team():
    roster = grok_bots.load_roster(REPO)
    roster["roles"] = [r for r in roster["roles"] if r.get("slug") != "costanza"]
    errors = grok_bots.check_roster(REPO, roster)
    assert any("missing team slugs" in e for e in errors)


def test_profile_does_not_dump_secret_gm_file():
    roster = grok_bots.load_roster(REPO)
    role = next(r for r in roster["roles"] if r.get("slug") == "costanza")
    text = grok_bots.profile_text(REPO, role)
    full = (REPO / "teams" / "costanza" / "general-manager.md").read_text()
    assert "GM Costanza" in text
    assert "pack" in text.lower()
    # Public bio is allowed; the long strategy body is not the profile.
    assert "## Football Philosophy" not in text
    assert len(text) < len(full)


def test_cli_check_and_run_sheet():
    assert grok_bots_cli.main(["--root", str(REPO), "check"]) == 0
    assert grok_bots_cli.main([
        "--root", str(REPO), "run-sheet", "--week", "1", "--run", "waivers",
    ]) == 0


def test_cli_routines_and_ops():
    assert grok_bots_cli.main(["--root", str(REPO), "routines"]) == 0
    assert grok_bots_cli.main([
        "--root", str(REPO), "ops", "--date", "2026-09-13",
    ]) == 0
    import pytest
    with pytest.raises(SystemExit) as exc:
        grok_bots_cli.main(["--help"])
    assert exc.value.code == 0

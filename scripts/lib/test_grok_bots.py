"""Tests for config/grok-bots.json isolation."""
from __future__ import annotations

from pathlib import Path

import grok_bots as grok_bots_cli
from lib import grok_bots

REPO = Path(__file__).resolve().parents[2]


def test_committed_roster_passes_check():
    assert grok_bots.check_roster(REPO) == []


def test_owned_teams_are_first_class_grok_bots():
    roster = grok_bots.load_roster(REPO)
    assert grok_bots.off_disk_slugs(roster) == []
    assert roster["isolation"].get("owned_team_slugs") == ["your-team", "wifes-team"]
    assert not roster["isolation"].get("owned_teams_off_disk")
    slugs = {role["slug"] for role in grok_bots.gm_roles(roster)}
    assert "your-team" in slugs
    assert "wifes-team" in slugs
    for role in grok_bots.gm_roles(roster):
        assert role["computer"] == "shared"
        assert role["product"] == "grok_bot"
        assert role["off_shared_disk"] is False
        assert role["own_gm_file_in_pack_only"] is True


def test_media_and_scout_never_read_gm_files():
    roster = grok_bots.load_roster(REPO)
    for role in grok_bots.roles(roster):
        if role["kind"] in ("media", "scout"):
            assert role["never_read_gm_files"] is True


def test_check_rejects_owned_gm_left_as_cursor():
    roster = grok_bots.load_roster(REPO)
    for role in roster["roles"]:
        if role.get("slug") == "your-team":
            role["computer"] = "none"
            role["off_shared_disk"] = True
            role["product"] = "cursor"
    errors = grok_bots.check_roster(REPO, roster)
    assert any("Grok Bot" in e or "product=grok_bot" in e for e in errors)


def test_check_rejects_stale_owned_teams_off_disk():
    roster = grok_bots.load_roster(REPO)
    roster["isolation"]["owned_teams_off_disk"] = ["your-team", "wifes-team"]
    errors = grok_bots.check_roster(REPO, roster)
    assert any("owned_teams_off_disk is retired" in e for e in errors)


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


def test_cli_prompt_builds_owned_team_packs(capsys):
    for slug in ("your-team", "wifes-team"):
        assert grok_bots_cli.main([
            "--root", str(REPO), "prompt", "--week", "1", "--run", "lineups",
            "--slug", slug, "--window", "main",
        ]) == 0
        out = capsys.readouterr().out
        assert slug in out or "Ed" in out or "Tony" in out
        assert out.strip()


def test_skills_teach_cloud_agents_owner_rule():
    for name in (
        "skill-commish.md",
        "skill-gm.md",
        "skill-scout.md",
        "skill-media.md",
        "README.md",
        "routines.md",
        "routines-gm.md",
        "routines-other.md",
    ):
        text = (REPO / "bots" / name).read_text(encoding="utf-8")
        assert "Cloud Agent" in text, name
        assert "Do not connect" not in text, name
        assert "GitHub plugin" not in text, name
        assert "never clone" in text.lower() or "do not clone" in text.lower() or "never git" in text.lower(), name
    rule = (REPO / "docs" / "skills" / "cloud-agents.md").read_text(
        encoding="utf-8"
    )
    assert "Cursor Cloud Agents" in rule
    assert "GitHub MCP connector" in rule
    assert "gh auth login" in rule
    assert "device login" in rule
    assert "straight to `main`" in rule
    assert "github-connector-only-43f8" in rule
    roster = grok_bots.load_roster(REPO)
    assert "Cursor Cloud Agents" in roster["isolation"]["rule"]
    assert "gh auth login" in roster["isolation"]["rule"]
    commish = next(r for r in roster["roles"] if r["kind"] == "commissioner")
    profile = grok_bots.profile_text(REPO, commish)
    assert "Cloud Agent" in profile
    assert "Clone this repo" not in profile
    gm = next(r for r in roster["roles"] if r.get("slug") == "costanza")
    gm_profile = grok_bots.profile_text(REPO, gm)
    assert "never clone git" in gm_profile
    assert "Cloud Agent" in gm_profile
    assert "Packs arrive in chat" in gm_profile

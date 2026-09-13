"""Who may see what. These are rule tests, not plumbing tests.

CLAUDE.md rule 1 and agents/media.md are enforced by which pack a role is
handed, so the pack builders are where that rule actually lives.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import role_packs  # noqa: E402


def _league(tmp_path):
    root = tmp_path
    (root / "teams" / "costanza" / "press").mkdir(parents=True)
    (root / "teams" / "dumbledore" / "press").mkdir(parents=True)
    (root / "teams" / "_template").mkdir(parents=True)
    for slug, secret in (("costanza", "SECRET-COSTANZA-DOCTRINE"),
                         ("dumbledore", "SECRET-DUMBLEDORE-DOCTRINE")):
        (root / "teams" / slug / "general-manager.md").write_text(
            f"# GM\n{secret}\n", encoding="utf-8")
        (root / "teams" / slug / "press" / "2026-w02.md").write_text(
            f"{slug} press\n", encoding="utf-8")
    (root / "state" / "weeks" / "2026-w02").mkdir(parents=True)
    (root / "state" / "forum").mkdir(parents=True)
    (root / "state" / "news" / "buzz").mkdir(parents=True)
    (root / "state" / "standings.json").write_text('{"teams":{}}', encoding="utf-8")
    (root / "state" / "transactions.jsonl").write_text(
        json.dumps({"season": "2026", "week": 2, "kind": "add"}) + "\n"
        + json.dumps({"season": "2026", "week": 1, "kind": "old"}) + "\n",
        encoding="utf-8")
    return root


def test_media_never_receives_a_gm_file(tmp_path):
    root = _league(tmp_path)
    pack = role_packs.build_media_pack(root, 2, "2026")
    blob = json.dumps(pack)
    assert "general_manager_files" not in pack
    assert "SECRET-COSTANZA-DOCTRINE" not in blob
    assert "SECRET-DUMBLEDORE-DOCTRINE" not in blob


def test_media_gets_the_public_record(tmp_path):
    root = _league(tmp_path)
    (root / "state" / "news" / "buzz" / "2026-w02.md").write_text(
        "- somebody is hyped\n", encoding="utf-8")
    pack = role_packs.build_media_pack(root, 2, "2026")
    assert "somebody is hyped" in pack["buzz"]
    assert pack["press"]["costanza"].strip() == "costanza press"
    assert [t["kind"] for t in pack["transactions_this_week"]] == ["add"]


def test_commissioner_is_the_sole_exception(tmp_path):
    root = _league(tmp_path)
    pack = role_packs.build_commissioner_pack(root, 2, "2026", stage="waivers")
    assert set(pack["general_manager_files"]) == {"costanza", "dumbledore"}
    assert "SECRET-COSTANZA-DOCTRINE" in json.dumps(pack)


def test_commissioner_gm_files_can_be_withheld(tmp_path):
    root = _league(tmp_path)
    pack = role_packs.build_commissioner_pack(
        root, 2, "2026", stage="waivers", include_gm_files=False)
    assert "general_manager_files" not in pack
    assert "SECRET-COSTANZA-DOCTRINE" not in json.dumps(pack)


def test_template_team_is_never_a_team(tmp_path):
    root = _league(tmp_path)
    assert "_template" not in role_packs.team_slugs(root)


def test_stage_decides_the_commissioner_inputs(tmp_path):
    root = _league(tmp_path)
    week = root / "state" / "weeks" / "2026-w02"
    (week / "faab-report.json").write_text('{"awards":[]}', encoding="utf-8")
    (week / "matchups.json").write_text('{"games":[]}', encoding="utf-8")
    (week / "lineups.json").write_text(
        '{"costanza":{"fallback":true},"dumbledore":{"fallback":false}}',
        encoding="utf-8")

    waivers = role_packs.build_commissioner_pack(root, 2, "2026", stage="waivers")
    assert "faab_report_dry_run" in waivers and "matchups" not in waivers

    recap = role_packs.build_commissioner_pack(root, 2, "2026", stage="recap")
    assert recap["fallback_teams"] == ["costanza"]
    assert "matchups" in recap


def test_missing_inputs_are_omitted_not_faked(tmp_path):
    """Week 1 has no recap, no buzz and no forum. That is legal, not an error."""
    root = _league(tmp_path)
    pack = role_packs.build_media_pack(root, 1, "2026")
    assert pack["buzz"] == ""
    assert pack["forum_this_week"] == []
    assert "last_recap" not in pack  # week 1 has no previous week at all


def test_decisions_are_collected_for_review(tmp_path):
    root = _league(tmp_path)
    dec = root / "state" / "weeks" / "2026-w02" / "decisions"
    dec.mkdir()
    (dec / "costanza.json").write_text('{"claims":[]}', encoding="utf-8")
    (dec / "dumbledore.lineup-main.json").write_text('{"starters":{}}',
                                                     encoding="utf-8")
    pack = role_packs.build_commissioner_pack(root, 2, "2026", stage="waivers")
    assert set(pack["decisions"]) == {"costanza.json",
                                      "dumbledore.lineup-main.json"}

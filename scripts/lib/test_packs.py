"""Tests for lineup windows, NFL slate, and GM packs."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import nfl_slate  # noqa: E402
from lib import packs  # noqa: E402
from lib.lineup_windows import freeze_violations, merge_lineup, slot_is_frozen  # noqa: E402


def test_window_for_date_splits_early_and_main():
    assert nfl_slate.window_for_date(date(2026, 9, 10)) == "early"  # Thursday
    assert nfl_slate.window_for_date(date(2026, 9, 9)) == "early"   # Wednesday
    assert nfl_slate.window_for_date(date(2026, 9, 13)) == "main"   # Sunday
    assert nfl_slate.window_for_date(date(2026, 9, 14)) == "main"   # Monday


def test_index_and_kicked():
    games = [
        {"date": "2026-09-10", "home": "KC", "away": "LAC", "status": "complete", "week": 1},
        {"date": "2026-09-13", "home": "DET", "away": "CHI", "status": "pre_game", "week": 1},
    ]
    by_team = nfl_slate.index_games_by_team(games)
    assert by_team["KC"]["away"] == "LAC"
    assert by_team["LAC"]["home"] == "KC"
    assert nfl_slate.game_has_kicked(by_team["KC"]) is True
    assert nfl_slate.game_has_kicked(by_team["DET"]) is False


def test_trim_free_agents_caps_per_position():
    fa = {}
    for i in range(20):
        fa[f"wr{i}"] = {"name": f"WR{i}", "pos": "WR", "proj_pts": float(i)}
        fa[f"rb{i}"] = {"name": f"RB{i}", "pos": "RB", "proj_pts": float(i)}
    trimmed = packs.trim_free_agents(fa, per_pos=3)
    assert len([k for k in trimmed if k.startswith("wr")]) == 3
    assert "wr19" in trimmed and "wr17" in trimmed
    assert "wr0" not in trimmed
    assert len(trimmed) == 6


def test_merge_lineup_early_locks_only_early_games():
    by_team = nfl_slate.index_games_by_team([
        {"date": "2026-09-10", "home": "KC", "away": "LAC", "status": "pre_game", "week": 1},
        {"date": "2026-09-13", "home": "DET", "away": "CHI", "status": "pre_game", "week": 1},
    ])
    resolved = {
        "kelce": {"id": "kelce", "nfl": "KC"},
        "stbrown": {"id": "stbrown", "nfl": "DET"},
    }
    entry = merge_lineup(
        None,
        {"TE": "kelce", "WR1": "stbrown"},
        "early",
        resolved,
        by_team,
        justification="TNF lock",
    )
    assert entry["starters"]["TE"] == "kelce"
    assert entry["starters"]["WR1"] == "stbrown"
    assert "TE" in entry["locked_slots"]
    assert "WR1" not in entry["locked_slots"]
    assert entry["windows_run"] == ["early"]


def test_main_window_cannot_move_frozen_thursday_slot():
    by_team = nfl_slate.index_games_by_team([
        {"date": "2026-09-10", "home": "KC", "away": "LAC", "status": "complete", "week": 1},
        {"date": "2026-09-13", "home": "DET", "away": "CHI", "status": "pre_game", "week": 1},
    ])
    resolved = {
        "kelce": {"id": "kelce", "nfl": "KC"},
        "otherte": {"id": "otherte", "nfl": "CHI"},
        "stbrown": {"id": "stbrown", "nfl": "DET"},
    }
    early = merge_lineup(
        None, {"TE": "kelce", "WR1": "stbrown"}, "early", resolved, by_team, "early"
    )
    errors = freeze_violations(early, {"TE": "otherte", "WR1": "stbrown"}, resolved, by_team)
    assert errors
    merged = merge_lineup(
        early, {"TE": "otherte", "WR1": "stbrown"}, "main", resolved, by_team, "main"
    )
    assert merged["starters"]["TE"] == "kelce"
    assert merged["starters"]["WR1"] == "stbrown"
    assert "WR1" in merged["locked_slots"]


def test_kicked_game_is_frozen_even_without_prior_window():
    by_team = nfl_slate.index_games_by_team([
        {"date": "2026-09-10", "home": "KC", "away": "LAC", "status": "in_game", "week": 1},
    ])
    resolved = {"kelce": {"id": "kelce", "nfl": "KC"}}
    assert slot_is_frozen("TE", None, resolved["kelce"], by_team) is True


def test_private_pack_does_not_open_other_gm_files(tmp_path: Path):
    """Isolation: building your-team must not require (or include) another GM file."""
    root = tmp_path
    (root / "teams" / "your-team").mkdir(parents=True)
    (root / "teams" / "kardashian").mkdir()
    (root / "state" / "weeks" / "2026-w02").mkdir(parents=True)
    (root / "teams" / "your-team" / "general-manager.md").write_text("You are Ed.\n")
    (root / "teams" / "your-team" / "roster.json").write_text(json.dumps({
        "team": "Flint Tropics", "faab_remaining": 50,
        "starters": {"QB": "p1"}, "bench": [], "ir": [],
    }))
    (root / "teams" / "your-team" / "opinions.json").write_text(json.dumps({
        "kardashian": {"stance": "wary", "take": "nope", "hooks": ["x"]},
    }))
    (root / "teams" / "kardashian" / "general-manager.md").write_text("SECRET KIM FILE\n")
    (root / "state" / "league-board.json").write_text(json.dumps({
        "your-team": {
            "faab_remaining": 50,
            "starters": {"QB": {"id": "p1", "name": "QB", "pos": "QB", "nfl": "KC",
                                "proj_pts": 18, "status": "Active", "injury": None}},
            "bench": [], "ir": [],
        },
        "kardashian": {
            "faab_remaining": 10,
            "starters": {"QB": {"id": "p2", "name": "Other", "pos": "QB", "nfl": "MIA",
                                "proj_pts": 12, "status": "Active", "injury": None}},
            "bench": [], "ir": [],
        },
    }))
    (root / "state" / "free-agents.json").write_text(json.dumps({
        "fa1": {"name": "FA", "pos": "WR", "proj_pts": 9.0},
    }))
    (root / "state" / "schedule.json").write_text(json.dumps({
        "regular_season": {"2": [["your-team", "kardashian"]]},
        "playoffs": {},
    }))
    (root / "state" / "news").mkdir()
    (root / "state" / "news" / "2026-w02.md").write_text("tabloid body")
    (root / "state" / "weeks" / "2026-w02" / "nfl-games.json").write_text(json.dumps([
        {"date": "2026-09-17", "home": "KC", "away": "NYG", "status": "pre_game", "week": 2},
    ]))

    private = packs.build_private_pack(root, "your-team", 2, "2026", run="lineups", window="early")
    blob = json.dumps(private)
    assert "SECRET KIM FILE" not in blob
    assert "You are Ed." in private["general_manager_md"]
    assert private["opponent"] == "kardashian"
    assert private.get("gameday_note") == ""

    (root / "teams" / "your-team" / "notes").mkdir()
    (root / "teams" / "your-team" / "notes" / "2026-w02-early.md").write_text("Start the kid.\n")
    private2 = packs.build_private_pack(root, "your-team", 2, "2026", run="lineups", window="early")
    assert private2["gameday_note"] == "Start the kid."
    assert "pressure, not orders" in packs.render_gm_prompt(private2)
    assert private["public"]["free_agents_trimmed"] is None  # lineups diet
    assert "Do NOT open state/players.json" in packs.render_gm_prompt(private)


def test_private_pack_does_not_include_buzz_file(tmp_path: Path):
    root = tmp_path
    (root / "teams" / "your-team").mkdir(parents=True)
    (root / "teams" / "your-team" / "general-manager.md").write_text("Ed.\n")
    (root / "teams" / "your-team" / "roster.json").write_text(json.dumps({
        "team": "Flint Tropics", "faab_remaining": 50,
        "starters": {"QB": "p1"}, "bench": [], "ir": [],
    }))
    (root / "state" / "weeks" / "2026-w02").mkdir(parents=True)
    (root / "state" / "news" / "buzz").mkdir(parents=True)
    (root / "state" / "news" / "buzz" / "2026-w02.md").write_text("SECRET_BUZZ_COUNT=999\n")
    (root / "state" / "news" / "2026-w02.md").write_text("tabloid rewrite only")
    (root / "state" / "league-board.json").write_text(json.dumps({
        "your-team": {"faab_remaining": 50, "starters": {}, "bench": [], "ir": []},
    }))
    (root / "state" / "free-agents.json").write_text("{}")
    (root / "state" / "schedule.json").write_text(json.dumps({
        "regular_season": {"2": []}, "playoffs": {},
    }))
    private = packs.build_private_pack(root, "your-team", 2, "2026", run="waivers")
    assert "SECRET_BUZZ_COUNT=999" not in json.dumps(private)
    assert "tabloid rewrite only" in (private["public"]["tabloid"] or "")


def test_waiver_prompt_budget_on_committed_week1():
    """Regression: stuffing players.json into 12 GMs is megabytes; packs stay small."""
    root = Path(__file__).resolve().parents[2]
    fa = root / "state" / "free-agents.json"
    if not fa.exists():
        return
    public = packs.build_public_pack(root, 1, "2026")
    assert public["free_agents_trimmed_count"] <= 12 * len(packs.FA_POSITIONS)
    slugs = packs.team_slugs(root)
    if not slugs:
        return
    sizes = []
    for slug in slugs:
        private = packs.build_private_pack(
            root, slug, 1, "2026", public=public, run="waivers",
        )
        sizes.append(packs.pack_sizes(public, private)["prompt_bytes"])
    assert max(sizes) < 120_000
    assert min(sizes) > 40_000
    lineup = packs.build_private_pack(
        root, slugs[0], 1, "2026", public=public, run="lineups", window="main",
    )
    assert packs.pack_sizes(public, lineup)["prompt_bytes"] < 70_000

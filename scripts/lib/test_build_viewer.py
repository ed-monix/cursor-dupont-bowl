"""Tests for scripts/build_viewer.py pure mappers and loaders. No network."""

import json
import pathlib
import tempfile
import build_viewer


PLAYERS = {
    "p1": {"name": "Star QB", "pos": "QB", "team": "KC"},
    "p2": {"name": "Bell Cow", "pos": "RB", "team": "DET"},
    "p3": {"name": "Bye Week WR", "pos": "WR", "team": "BUF"},
}


def make_team(slug, total, scores, stat_lines, starters):
    return {"slug": slug, "roster": {"starters": starters}, "scores": scores,
            "stat_lines": stat_lines, "total": total, "starters_yet_to_play": 0}


def test_viewer_starters_marks_played_and_carries_meta():
    team = make_team(
        "dynamos", 24.0,
        scores={"p1": 20.0, "p2": 4.0, "p3": 0.0},
        stat_lines={"p1": {"pass_yd": 300, "pass_td": 2}, "p2": {"rush_yd": 40}},
        starters={"QB": "p1", "RB1": "p2", "WR1": "p3", "WR2": None})
    rows = build_viewer.viewer_starters(team, PLAYERS)
    by = {r["slot"]: r for r in rows}
    assert "WR2" not in by                       # null slot omitted
    assert by["QB"]["played"] is True
    assert by["QB"]["name"] == "Star QB" and by["QB"]["nfl"] == "KC"
    assert "300" in by["QB"]["stat"]             # stat summary present
    assert by["WR1"]["played"] is False          # no stat line -> yet to play
    assert by["WR1"]["stat"] == ""


def test_viewer_matchup_maps_leader_slug_to_side():
    home = make_team("dynamos", 100.0, {"p1": 100.0}, {"p1": {"pass_yd": 250}}, {"QB": "p1"})
    away = make_team("wagon", 80.0, {"p2": 80.0}, {"p2": {"rush_yd": 120}}, {"RB1": "p2"})
    m = {"home_team": home, "away_team": away, "leader_slug": "dynamos"}
    v = build_viewer.viewer_matchup(m, PLAYERS, {"dynamos": "3-0", "wagon": "1-2"})
    assert v["leader"] == "home"
    assert v["home"]["name"] == "Dynamos" and v["home"]["record"] == "3-0"
    assert v["away"]["name"] == "Wagon"

    m_tie = {"home_team": home, "away_team": away, "leader_slug": None}
    assert build_viewer.viewer_matchup(m_tie, PLAYERS, {})["leader"] is None


def test_viewer_standings_sorted_by_record_then_points_for():
    standings_json = {"teams": {
        "a": {"wins": 2, "losses": 1, "ties": 0, "points_for": 300.0, "points_against": 280.0},
        "b": {"wins": 2, "losses": 1, "ties": 0, "points_for": 320.0, "points_against": 275.0},
        "c": {"wins": 3, "losses": 0, "ties": 0, "points_for": 290.0, "points_against": 250.0},
    }}
    rows = build_viewer.viewer_standings(standings_json)
    # c leads (3 wins); then b over a (same record, higher PF).
    assert [r["slug"] for r in rows] == ["c", "b", "a"]
    assert rows[1]["pf"] == 320.0


def test_pretty_name():
    assert build_viewer.pretty("last-place-luxury") == "Last Place Luxury"


def test_display_name_prefers_franchise_name_over_pretty():
    names = {"rinna": "Reunion Special"}
    # A team that chose a name shows it; one that didn't falls back to pretty.
    assert build_viewer._display_name("rinna", names) == "Reunion Special"
    assert build_viewer._display_name("your-team", names) == "Your Team"
    assert build_viewer._display_name("rinna", None) == "Rinna"


def test_viewer_matchup_uses_franchise_names_when_provided():
    home = make_team("dynamos", 100.0, {"p1": 100.0}, {"p1": {"pass_yd": 250}}, {"QB": "p1"})
    away = make_team("wagon", 80.0, {"p2": 80.0}, {"p2": {"rush_yd": 120}}, {"RB1": "p2"})
    m = {"home_team": home, "away_team": away, "leader_slug": "dynamos"}
    v = build_viewer.viewer_matchup(m, PLAYERS, {"dynamos": "3-0", "wagon": "1-2"},
                                    {"dynamos": "The Dynamo Drop"})
    assert v["home"]["name"] == "The Dynamo Drop"  # franchise name
    assert v["away"]["name"] == "Wagon"            # no name -> pretty fallback


# --- Tests for helper functions (Section, Frontmatter) ----------------------


def test_section_extracts_heading_body():
    """_section extracts content under a heading up to the next ##."""
    md = """# Title

## Mission

This is the mission.
It spans multiple lines.

## Other Section
Some other stuff."""
    result = build_viewer._section(md, "Mission")
    assert "This is the mission" in result
    assert "It spans multiple lines" in result
    assert "Other Section" not in result


def test_section_stops_at_next_heading():
    """_section stops at the next ## heading."""
    md = """## Section One
Line 1
Line 2

## Section Two
Line 3"""
    result = build_viewer._section(md, "Section One")
    assert "Line 1" in result
    assert "Line 2" in result
    assert "Section Two" not in result
    assert "Line 3" not in result


def test_section_returns_empty_when_not_found():
    """_section returns empty string if heading not found."""
    md = """## Present
Content"""
    result = build_viewer._section(md, "Missing")
    assert result == ""


def test_section_handles_empty_input():
    """_section handles empty input gracefully."""
    assert build_viewer._section("", "Heading") == ""
    assert build_viewer._section("Some text", "") == ""


def test_frontmatter_description_extracts_value():
    """_frontmatter_description extracts description from YAML frontmatter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "test.md"
        path.write_text("""---
description: Test description here
other_field: value
---

# Content
Body""")
        result = build_viewer._frontmatter_description(path)
        assert result == "Test description here"


def test_frontmatter_description_handles_quoted_values():
    """_frontmatter_description strips quotes from description."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "test.md"
        path.write_text('''---
description: "Quoted description"
---

# Content''')
        result = build_viewer._frontmatter_description(path)
        assert result == "Quoted description"


def test_frontmatter_description_returns_empty_when_missing():
    """_frontmatter_description returns empty if description not found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "test.md"
        path.write_text("""---
other_field: value
---

# Content""")
        result = build_viewer._frontmatter_description(path)
        assert result == ""


def test_frontmatter_description_returns_empty_for_missing_file():
    """_frontmatter_description returns empty if file doesn't exist."""
    path = pathlib.Path("/nonexistent/path/file.md")
    result = build_viewer._frontmatter_description(path)
    assert result == ""


# --- Tests for Feed Loader ---------------------------------------------------


def test_load_feed_tabloid_and_recap():
    """_load_feed loads tabloid and recap from markdown files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "state" / "news").mkdir(parents=True)
        (root / "state" / "weeks" / "2026-w05").mkdir(parents=True)

        # Create tabloid
        tabloid_path = root / "state" / "news" / "2026-w05.md"
        tabloid_path.write_text("# Week 5 Tabloid\nContent here")

        # Create recap
        recap_path = root / "state" / "weeks" / "2026-w05" / "recap.md"
        recap_path.write_text("# Week 5 Recap\nRecap content")

        # Mock ROOT to use tmpdir
        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            feed = build_viewer._load_feed("2026", 5)
            assert "Week 5 Tabloid" in feed["tabloid"]
            assert "Week 5 Recap" in feed["recap"]
            assert feed["forum"] == []
        finally:
            build_viewer.ROOT = original_root


def test_load_feed_forum_newest_first_with_names():
    """_load_feed loads forum posts reversed (newest first) with names added."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "state" / "forum").mkdir(parents=True)
        (root / "state" / "news").mkdir(parents=True)
        (root / "state" / "weeks" / "2026-w05").mkdir(parents=True)

        # Create forum thread with two posts
        forum_path = root / "state" / "forum" / "2026-w05.jsonl"
        forum_path.write_text(
            '{"timestamp": "2026-08-01T10:00:00Z", "team": "team-a", "post": "First post"}\n'
            '{"timestamp": "2026-08-01T11:00:00Z", "team": "team-b", "post": "Second post"}\n'
        )

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            feed = build_viewer._load_feed("2026", 5)
            assert len(feed["forum"]) == 2
            # Should be reversed (newest first)
            assert feed["forum"][0]["post"] == "Second post"
            assert feed["forum"][0]["team"] == "team-b"
            assert feed["forum"][0]["name"] == "Team B"  # pretty(slug)
            assert feed["forum"][1]["post"] == "First post"
            assert feed["forum"][1]["name"] == "Team A"
        finally:
            build_viewer.ROOT = original_root


def test_load_feed_handles_missing_files():
    """_load_feed returns empty strings when files are missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "state" / "forum").mkdir(parents=True)

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            feed = build_viewer._load_feed("2026", 5)
            assert feed["tabloid"] == ""
            assert feed["recap"] == ""
            assert feed["forum"] == []
        finally:
            build_viewer.ROOT = original_root


# --- Tests for Guide Loader --------------------------------------------------


def test_load_guide_mission_from_readme():
    """_load_guide extracts mission from README.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        readme = root / "README.md"
        readme.write_text("""# Title

## Mission

Have fun. Let chaos happen.

## Other Section
Other content""")

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            assert "Have fun" in guide["mission"]
            assert "chaos" in guide["mission"]
        finally:
            build_viewer.ROOT = original_root


def test_load_guide_rules_from_league_rules():
    """_load_guide loads full verbatim contents of league-rules.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "config").mkdir(parents=True)
        rules_path = root / "config" / "league-rules.md"
        rules_path.write_text("# League Rules\n\n12 teams. Half-PPR scoring.")

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            assert "League Rules" in guide["rules"]
            assert "12 teams" in guide["rules"]
        finally:
            build_viewer.ROOT = original_root


def test_load_guide_cast_includes_teams_commissioner_media():
    """_load_guide builds cast with teams, commissioner, and media."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "teams" / "team-a").mkdir(parents=True)
        (root / "teams" / "team-b").mkdir(parents=True)
        (root / "teams" / "_template").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "state" / "weeks" / "2026-w01").mkdir(parents=True)

        # Create GM files with Public bio sections
        gm_a = root / "teams" / "team-a" / "general-manager.md"
        gm_a.write_text("""# GM A

## Public bio
Team A's GM is decisive.

## Football Philosophy
Win now.""")

        gm_b = root / "teams" / "team-b" / "general-manager.md"
        gm_b.write_text("""# GM B

## Public bio
Team B loves chaos.

## Other""")

        # Create commissioner
        commissioner = root / "agents" / "commissioner.md"
        commissioner.write_text("""# The Commissioner

You are the Commissioner. Scrupulously fair.

## Jurisdiction
Review everything.""")

        # Create media
        media = root / "agents" / "media.md"
        media.write_text("""# Kris Jenner

You are Kris Jenner. This league is your show.

## Jurisdiction
You hold ZERO powers.""")

        # Create standings
        standings = root / "state" / "standings.json"
        standings.write_text(json.dumps({
            "teams": {
                "team-a": {"wins": 3, "losses": 1, "ties": 0},
                "team-b": {"wins": 2, "losses": 2, "ties": 0},
            }
        }))

        # Create league-rules.md
        rules = root / "config" / "league-rules.md"
        rules.write_text("# Rules\n\n12 teams.")

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            cast = guide["cast"]

            # Should have 2 teams + commissioner + media = 4
            assert len(cast) == 4

            # Check team-a
            team_a = next((c for c in cast if c["slug"] == "team-a"), None)
            assert team_a is not None
            assert team_a["name"] == "Team A"
            assert team_a["kind"] == "ai"
            assert team_a["record"] == "3-1"
            assert "decisive" in team_a["bio"]

            # Check team-b
            team_b = next((c for c in cast if c["slug"] == "team-b"), None)
            assert team_b is not None
            assert team_b["record"] == "2-2"

            # Check commissioner
            commissioner_entry = next((c for c in cast if c["slug"] == "commissioner"), None)
            assert commissioner_entry is not None
            assert commissioner_entry["name"] == "The Commissioner"
            assert commissioner_entry["kind"] == "official"
            assert commissioner_entry["record"] == ""
            assert "Scrupulously" in commissioner_entry["bio"]

            # Check media
            media_entry = next((c for c in cast if c["slug"] == "media"), None)
            assert media_entry is not None
            assert media_entry["name"] == "Kris Jenner"
            assert media_entry["kind"] == "media"
            assert "show" in media_entry["bio"]

        finally:
            build_viewer.ROOT = original_root


def test_load_guide_human_teams_kind():
    """_load_guide marks your-team and wifes-team as human kind."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "teams" / "your-team").mkdir(parents=True)
        (root / "teams" / "wifes-team").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "state").mkdir(parents=True)

        # Minimal agent and config files
        (root / "agents" / "commissioner.md").write_text("# Commissioner\n\nContent")
        (root / "agents" / "media.md").write_text("# Media\n\nContent")
        (root / "config" / "league-rules.md").write_text("# Rules")
        (root / "state" / "standings.json").write_text(json.dumps({"teams": {}}))

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            cast = guide["cast"]

            your_team = next((c for c in cast if c["slug"] == "your-team"), None)
            assert your_team is not None
            assert your_team["kind"] == "human"

            wifes_team = next((c for c in cast if c["slug"] == "wifes-team"), None)
            assert wifes_team is not None
            assert wifes_team["kind"] == "human"

        finally:
            build_viewer.ROOT = original_root


def test_load_guide_cast_fallback_signing_in_progress():
    """_load_guide uses 'Signing in progress' when GM file or bio section is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "teams" / "team-a").mkdir(parents=True)
        (root / "teams" / "team-b").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "state").mkdir(parents=True)

        # team-a has no GM file
        # team-b has GM file but no Public bio section
        (root / "teams" / "team-b" / "general-manager.md").write_text("""# GM B

## Other Section
No bio here.""")

        (root / "agents" / "commissioner.md").write_text("# Commissioner\n\nContent")
        (root / "agents" / "media.md").write_text("# Media\n\nContent")
        (root / "config" / "league-rules.md").write_text("# Rules")
        (root / "state" / "standings.json").write_text(json.dumps({"teams": {}}))

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            cast = guide["cast"]

            team_a = next((c for c in cast if c["slug"] == "team-a"), None)
            assert team_a["bio"] == "Signing in progress"

            team_b = next((c for c in cast if c["slug"] == "team-b"), None)
            assert team_b["bio"] == "Signing in progress"

        finally:
            build_viewer.ROOT = original_root


def test_load_guide_cast_record_with_ties():
    """_load_guide formats record as W-L or W-L-T."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / "teams" / "team-a").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "state").mkdir(parents=True)

        (root / "agents" / "commissioner.md").write_text("# Commissioner\n\nContent")
        (root / "agents" / "media.md").write_text("# Media\n\nContent")
        (root / "config" / "league-rules.md").write_text("# Rules")

        # Team with ties
        standings = root / "state" / "standings.json"
        standings.write_text(json.dumps({
            "teams": {
                "team-a": {"wins": 3, "losses": 1, "ties": 1},
            }
        }))

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            cast = guide["cast"]
            team_a = next((c for c in cast if c["slug"] == "team-a"), None)
            assert team_a["record"] == "3-1-1"

        finally:
            build_viewer.ROOT = original_root


def test_load_guide_how_it_runs_from_command_frontmatter():
    """_load_guide extracts command descriptions from frontmatter in order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / ".claude" / "commands").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "state").mkdir(parents=True)

        # Create command files with frontmatter
        for cmd, desc in [
            ("notes", "Scaffold owner notes"),
            ("saturday", "Waivers and trades"),
            ("sunday", "Lock lineups"),
            ("recap", "Final results"),
            ("refresh-board", "Sync and publish"),
        ]:
            cmd_file = root / ".claude" / "commands" / f"{cmd}.md"
            cmd_file.write_text(f'''---
description: {desc}
---

# /{cmd} command

Content here''')

        (root / "agents" / "commissioner.md").write_text("# Commissioner\n\nContent")
        (root / "agents" / "media.md").write_text("# Media\n\nContent")
        (root / "config" / "league-rules.md").write_text("# Rules")
        (root / "state" / "standings.json").write_text(json.dumps({"teams": {}}))

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            how_it_runs = guide["howItRuns"]

            assert len(how_it_runs) == 5
            assert how_it_runs[0]["cmd"] == "/notes"
            assert how_it_runs[0]["desc"] == "Scaffold owner notes"
            assert how_it_runs[1]["cmd"] == "/saturday"
            assert how_it_runs[1]["desc"] == "Waivers and trades"
            assert how_it_runs[2]["cmd"] == "/sunday"
            assert how_it_runs[2]["desc"] == "Lock lineups"

        finally:
            build_viewer.ROOT = original_root


def test_load_guide_skips_missing_command_files():
    """_load_guide skips command files that don't exist or have no description."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        (root / ".claude" / "commands").mkdir(parents=True)
        (root / "agents").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "state").mkdir(parents=True)

        # Only create notes and recap commands (missing saturday, sunday, refresh-board)
        (root / ".claude" / "commands" / "notes.md").write_text("""---
description: Scaffold notes
---
# Content""")
        (root / ".claude" / "commands" / "recap.md").write_text("""---
description: Final recap
---
# Content""")

        (root / "agents" / "commissioner.md").write_text("# Commissioner\n\nContent")
        (root / "agents" / "media.md").write_text("# Media\n\nContent")
        (root / "config" / "league-rules.md").write_text("# Rules")
        (root / "state" / "standings.json").write_text(json.dumps({"teams": {}}))

        original_root = build_viewer.ROOT
        build_viewer.ROOT = root
        try:
            guide = build_viewer._load_guide("2026")
            how_it_runs = guide["howItRuns"]

            # Should have only notes and recap (in order from the list, but only the ones found)
            cmds = [h["cmd"] for h in how_it_runs]
            assert "/notes" in cmds
            assert "/recap" in cmds
            assert "/saturday" not in cmds
            assert "/sunday" not in cmds

        finally:
            build_viewer.ROOT = original_root

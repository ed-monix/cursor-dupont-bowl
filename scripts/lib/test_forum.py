"""Tests for scripts/forum.py. Uses tmpdir for isolation, pure I/O."""

import json
import pathlib
import tempfile

import forum
from lib.decisions import load_schema, validate


def test_append_post_writes_well_formed_jsonl_line(tmp_path):
    """append_post creates state/forum/ and writes a valid JSON line."""
    root = tmp_path
    forum.append_post(root, week=1, team="team-a", post="Let's go!", season="2026",
                      timestamp="2026-01-01T12:00:00+00:00")

    # Verify directory and file exist.
    forum_file = root / "state" / "forum" / "2026-w01.jsonl"
    assert forum_file.exists()

    # Read and parse the line.
    with open(forum_file, "r", encoding="utf-8") as f:
        line = f.read().strip()
    entry = json.loads(line)

    # Verify fields.
    assert entry["timestamp"] == "2026-01-01T12:00:00+00:00"
    assert entry["team"] == "team-a"
    assert entry["post"] == "Let's go!"


def test_read_thread_round_trips_appended_posts(tmp_path):
    """read_thread returns the posts that append_post wrote."""
    root = tmp_path

    # Append a few posts.
    forum.append_post(root, week=2, team="team-a", post="First post",
                      timestamp="2026-01-08T10:00:00+00:00")
    forum.append_post(root, week=2, team="team-b", post="Second post",
                      timestamp="2026-01-08T10:30:00+00:00")

    # Read them back.
    thread = forum.read_thread(root, week=2)

    assert len(thread) == 2
    assert thread[0] == {"timestamp": "2026-01-08T10:00:00+00:00",
                         "team": "team-a", "post": "First post"}
    assert thread[1] == {"timestamp": "2026-01-08T10:30:00+00:00",
                         "team": "team-b", "post": "Second post"}


def test_one_post_per_team_per_week_enforced_raises_error(tmp_path):
    """Appending a second post by the same team raises ValueError."""
    root = tmp_path

    # First append succeeds.
    forum.append_post(root, week=3, team="team-c", post="First time",
                      timestamp="2026-01-15T09:00:00+00:00")

    # Second append by same team raises ValueError.
    try:
        forum.append_post(root, week=3, team="team-c", post="Second time",
                          timestamp="2026-01-15T09:30:00+00:00")
        assert False, "Expected ValueError for duplicate team post"
    except ValueError as e:
        assert "already posted" in str(e)
        assert "team-c" in str(e)


def test_different_teams_in_same_week_both_post(tmp_path):
    """Multiple teams can post in the same week; order is preserved."""
    root = tmp_path

    teams_and_posts = [
        ("team-a", "Post A", "2026-01-20T08:00:00+00:00"),
        ("team-b", "Post B", "2026-01-20T08:15:00+00:00"),
        ("team-c", "Post C", "2026-01-20T08:30:00+00:00"),
    ]

    for team, post, ts in teams_and_posts:
        forum.append_post(root, week=4, team=team, post=post, timestamp=ts)

    # Verify all three are present in order.
    thread = forum.read_thread(root, week=4)
    assert len(thread) == 3
    for i, (expected_team, expected_post, expected_ts) in enumerate(teams_and_posts):
        assert thread[i]["team"] == expected_team
        assert thread[i]["post"] == expected_post
        assert thread[i]["timestamp"] == expected_ts


def test_read_thread_missing_week_returns_empty_list(tmp_path):
    """read_thread returns [] if the week's file does not exist."""
    root = tmp_path
    thread = forum.read_thread(root, week=99, season="2026")
    assert thread == []


def test_read_thread_with_missing_forum_dir_returns_empty_list(tmp_path):
    """read_thread returns [] if state/forum/ directory does not exist."""
    root = tmp_path
    thread = forum.read_thread(root, week=1, season="2026")
    assert thread == []


def test_append_post_auto_timestamp_iso8601_format(tmp_path):
    """append_post with no timestamp param generates ISO8601 UTC timestamp."""
    root = tmp_path

    # Append without explicit timestamp.
    forum.append_post(root, week=5, team="team-d", post="Auto-timestamp test")

    thread = forum.read_thread(root, week=5)
    assert len(thread) == 1

    # Verify timestamp is ISO8601-ish (has 'T' and 'Z' or '+' indicating UTC).
    ts = thread[0]["timestamp"]
    assert "T" in ts
    assert (ts.endswith("Z") or "+" in ts or "-" in ts)


def test_append_post_respects_season_parameter(tmp_path):
    """append_post and read_thread correctly handle season parameter."""
    root = tmp_path

    # Append to two different seasons.
    forum.append_post(root, week=1, team="team-a", post="2025 post",
                      season="2025", timestamp="2025-01-01T00:00:00+00:00")
    forum.append_post(root, week=1, team="team-b", post="2026 post",
                      season="2026", timestamp="2026-01-01T00:00:00+00:00")

    # Read them separately.
    thread_2025 = forum.read_thread(root, week=1, season="2025")
    thread_2026 = forum.read_thread(root, week=1, season="2026")

    assert len(thread_2025) == 1
    assert thread_2025[0]["team"] == "team-a"

    assert len(thread_2026) == 1
    assert thread_2026[0]["team"] == "team-b"


def test_saturday_decision_schema_with_forum_post_validates(tmp_path):
    """saturday-decision schema accepts optional forum_post field."""
    schema = load_schema("saturday-decision")

    # Decision WITH forum_post should validate.
    decision_with_forum = {
        "claims": [],
        "drops": [],
        "note_reply": "Owner, here's my take.",
        "forum_post": "We're coming for first place!"
    }
    errors = validate(decision_with_forum, schema)
    assert errors == []


def test_saturday_decision_schema_without_forum_post_validates(tmp_path):
    """saturday-decision schema does not require forum_post (it's optional)."""
    schema = load_schema("saturday-decision")

    # Decision WITHOUT forum_post should also validate.
    decision_without_forum = {
        "claims": [],
        "drops": [],
        "note_reply": "Owner, here's my take."
    }
    errors = validate(decision_without_forum, schema)
    assert errors == []


def test_sunday_lineup_schema_with_forum_post_validates(tmp_path):
    """sunday-lineup schema accepts optional forum_post field."""
    schema = load_schema("sunday-lineup")

    # Lineup WITH forum_post should validate.
    lineup_with_forum = {
        "starters": {"QB": "p_1", "RB1": "p_2", "RB2": "p_3", "WR1": "p_4"},
        "justification": "This lineup will dominate!",
        "forum_post": "Can't wait to crush my opponent!"
    }
    errors = validate(lineup_with_forum, schema)
    assert errors == []


def test_sunday_lineup_schema_without_forum_post_validates(tmp_path):
    """sunday-lineup schema does not require forum_post (it's optional)."""
    schema = load_schema("sunday-lineup")

    # Lineup WITHOUT forum_post should also validate.
    lineup_without_forum = {
        "starters": {"QB": "p_1", "RB1": "p_2", "RB2": "p_3", "WR1": "p_4"},
        "justification": "This lineup will dominate!"
    }
    errors = validate(lineup_without_forum, schema)
    assert errors == []


def test_forum_post_not_required_in_saturday_decision():
    """Verify the schema does not list forum_post in required fields."""
    schema = load_schema("saturday-decision")
    assert "forum_post" not in schema.get("required", [])


def test_forum_post_not_required_in_sunday_lineup():
    """Verify the schema does not list forum_post in required fields."""
    schema = load_schema("sunday-lineup")
    assert "forum_post" not in schema.get("required", [])

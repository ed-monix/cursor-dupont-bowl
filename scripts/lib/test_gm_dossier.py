"""Tests for scripts/gm_dossier.py -- GM memory (review R1: dossier + press).

Hermetic: every test builds its own tmp_path repo skeleton (teams/, state/)
and passes it as `root` -- no dependency on real repo state, no network.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import gm_dossier


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_notes(root: pathlib.Path, slug: str, week: int, note: str, season: str = "2026") -> None:
    _write(root / "teams" / slug / "notes" / f"{season}-w{week:02d}.md", note)


def _write_transactions(root: pathlib.Path, entries: list) -> None:
    lines = [json.dumps(e) for e in entries]
    _write(root / "state" / "transactions.jsonl", "\n".join(lines) + "\n")


def _write_recap(root: pathlib.Path, week: int, text: str, season: str = "2026") -> None:
    _write(root / "state" / "weeks" / f"{season}-w{week:02d}" / "recap.md", text)


def _write_matchups(root: pathlib.Path, week: int, matchups: list, season: str = "2026") -> None:
    data = {"season": season, "week": week, "matchups": matchups}
    _write(root / "state" / "weeks" / f"{season}-w{week:02d}" / "matchups.json", json.dumps(data))


def _write_standings(root: pathlib.Path, teams: dict, season: str = "2026") -> None:
    data = {"season": season, "teams": teams}
    _write(root / "state" / "standings.json", json.dumps(data))


def _write_roster(root: pathlib.Path, slug: str, display_name: str) -> None:
    _write(root / "teams" / slug / "roster.json", json.dumps({"team": display_name}))


TXN = {
    "timestamp": "2026-09-06T12:00:00Z", "team": "team-chaos", "action": "waiver_claim",
    "players": ["p1"], "bid": 12, "reasoning": "needed a QB2", "status": "applied",
}


# ---------------------------------------------------------------------------
# append_press
# ---------------------------------------------------------------------------

def test_append_press_creates_file_and_folder(tmp_path):
    """append_press creates teams/<slug>/press/ and the week file from nothing."""
    path = gm_dossier.append_press(tmp_path, "team-chaos", 5, "First press statement.")

    assert path == tmp_path / "teams" / "team-chaos" / "press" / "2026-w05.md"
    assert path.is_file()
    assert "First press statement." in path.read_text(encoding="utf-8")


def test_append_press_appends_across_two_calls_with_separator(tmp_path):
    """A second call to the same team/week appends rather than overwriting,
    and the two blocks stay distinguishable (separated), not run together."""
    path = gm_dossier.append_press(tmp_path, "team-chaos", 5, "note_reply: whatever, coach.")
    gm_dossier.append_press(tmp_path, "team-chaos", 5, "outcome: won the bid at $23.")

    text = path.read_text(encoding="utf-8")
    assert "note_reply: whatever, coach." in text
    assert "outcome: won the bid at $23." in text
    # both blocks present and NOT concatenated into one run-on line
    first_end = text.index("note_reply: whatever, coach.") + len("note_reply: whatever, coach.")
    second_start = text.index("outcome: won the bid at $23.")
    between = text[first_end:second_start]
    assert between.count("\n") >= 2  # a real separator, not just a single newline


def test_append_press_only_touches_that_teams_own_dir(tmp_path):
    """append_press for one team never creates or touches another team's folder."""
    gm_dossier.append_press(tmp_path, "team-chaos", 5, "hello")

    assert not (tmp_path / "teams" / "team-order").exists()
    assert list((tmp_path / "teams").iterdir()) == [tmp_path / "teams" / "team-chaos"]


def test_append_press_week_int_and_zero_padded_string_agree(tmp_path):
    """Week 5 passed as int or as already-padded string lands in the same file."""
    p1 = gm_dossier.append_press(tmp_path, "team-chaos", 5, "a")
    p2 = gm_dossier.append_press(tmp_path, "team-chaos", "05", "b")
    assert p1 == p2


# ---------------------------------------------------------------------------
# build_dossier -- notes / replies
# ---------------------------------------------------------------------------

def test_build_dossier_includes_notes_and_gm_replies(tmp_path):
    """notes carries both the owner note text and the GM's press reply for that week."""
    _write_notes(tmp_path, "team-chaos", 4, "# Owner note\nBench your studs. I dare you.")
    gm_dossier.append_press(tmp_path, "team-chaos", 4, "note_reply: Never. -GM")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5, weeks_back=3)

    assert len(dossier["notes"]) == 1
    entry = dossier["notes"][0]
    assert entry["week"] == 4
    assert "Bench your studs" in entry["note"]
    assert "Never. -GM" in entry["press"]


def test_build_dossier_notes_most_recent_last(tmp_path):
    """Multiple note weeks come back oldest-first, most recent last (thread order)."""
    for wk, text in [(1, "week one note"), (2, "week two note"), (3, "week three note")]:
        _write_notes(tmp_path, "team-chaos", wk, text)

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=4, weeks_back=3)

    weeks = [e["week"] for e in dossier["notes"]]
    assert weeks == [1, 2, 3]
    assert dossier["notes"][-1]["note"] == "week three note"


def test_build_dossier_weeks_back_bounds_notes_window(tmp_path):
    """weeks_back=2 keeps only the 2 most recent eligible note weeks."""
    for wk in range(1, 6):
        _write_notes(tmp_path, "team-chaos", wk, f"note {wk}")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=6, weeks_back=2)

    weeks = [e["week"] for e in dossier["notes"]]
    assert weeks == [4, 5]


def test_build_dossier_current_week_excludes_this_weeks_note(tmp_path):
    """The dossier is the team's PAST -- a note for the week being decided is excluded."""
    _write_notes(tmp_path, "team-chaos", 5, "past week")
    _write_notes(tmp_path, "team-chaos", 6, "this week, not yet decided")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=6, weeks_back=3)

    weeks = [e["week"] for e in dossier["notes"]]
    assert weeks == [5]


def test_build_dossier_no_current_week_takes_latest_available(tmp_path):
    """current_week=None (unknown) still bounds to the most recent weeks_back weeks."""
    for wk in range(1, 5):
        _write_notes(tmp_path, "team-chaos", wk, f"note {wk}")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=None, weeks_back=2)

    weeks = [e["week"] for e in dossier["notes"]]
    assert weeks == [3, 4]


def test_build_dossier_missing_notes_dir_returns_empty_list(tmp_path):
    """No notes/ directory at all -> [] , never raises."""
    (tmp_path / "teams" / "team-chaos").mkdir(parents=True)

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5)

    assert dossier["notes"] == []


# ---------------------------------------------------------------------------
# build_dossier -- own_transactions / isolation
# ---------------------------------------------------------------------------

def test_build_dossier_own_transactions_only(tmp_path):
    """Only this team's transactions.jsonl entries come back; another team's are excluded."""
    mine = {**TXN, "reasoning": "mine"}
    other = {**TXN, "team": "team-order", "reasoning": "not mine"}
    _write_transactions(tmp_path, [mine, other, {**mine, "reasoning": "mine again"}])

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    reasonings = [e["reasoning"] for e in dossier["own_transactions"]]
    assert reasonings == ["mine", "mine again"]
    assert all(e["team"] == "team-chaos" for e in dossier["own_transactions"])
    assert "not mine" not in reasonings


def test_build_dossier_transactions_include_reasoning_field(tmp_path):
    """Transaction entries are handed back whole -- reasoning travels with them."""
    _write_transactions(tmp_path, [TXN])

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert dossier["own_transactions"][0]["reasoning"] == "needed a QB2"
    assert dossier["own_transactions"][0]["bid"] == 12


def test_build_dossier_transactions_capped_at_ten(tmp_path):
    """Even with weeks_back generous, own_transactions never exceeds the cap."""
    entries = [{**TXN, "reasoning": f"txn {i}"} for i in range(25)]
    _write_transactions(tmp_path, entries)

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", weeks_back=50)

    assert len(dossier["own_transactions"]) == gm_dossier.CAP_TRANSACTIONS == 10
    # most recent kept
    assert dossier["own_transactions"][-1]["reasoning"] == "txn 24"


def test_build_dossier_never_reads_another_teams_general_manager_file(tmp_path):
    """Isolation (CLAUDE.md rule 1): another team's GM file is present on disk
    but never shows up anywhere in the dossier, and build_dossier does not
    error out just because it exists."""
    _write(tmp_path / "teams" / "team-order" / "general-manager.md",
           "SECRET STRATEGY: never trade RBs.")
    _write_notes(tmp_path, "team-chaos", 1, "my own note")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=2)

    dumped = json.dumps(dossier)
    assert "SECRET STRATEGY" not in dumped
    assert "team-order" not in dumped


def test_build_dossier_missing_transactions_file_returns_empty_list(tmp_path):
    (tmp_path / "state").mkdir(parents=True)

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert dossier["own_transactions"] == []


def test_build_dossier_malformed_transaction_line_skipped_not_raised(tmp_path):
    """A corrupt line in transactions.jsonl is skipped, not fatal."""
    path = tmp_path / "state" / "transactions.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(TXN) + "\n" + "{not json\n", encoding="utf-8")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert len(dossier["own_transactions"]) == 1


# ---------------------------------------------------------------------------
# build_dossier -- recap_mentions
# ---------------------------------------------------------------------------

def test_build_dossier_recap_mentions_by_slug(tmp_path):
    _write_recap(tmp_path, 4, (
        "Week 4 recap.\n"
        "team-chaos blew a 30-point lead in stunning fashion.\n"
        "team-order cruised to another dull win.\n"
    ))

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5, weeks_back=3)

    lines = [m["line"] for m in dossier["recap_mentions"]]
    assert any("blew a 30-point lead" in line for line in lines)
    assert not any("team-order cruised" in line for line in lines)


def test_build_dossier_recap_mentions_by_display_name(tmp_path):
    """A team's own roster.json 'team' display name also counts as a mention,
    not just its slug."""
    _write_roster(tmp_path, "team-chaos", "The Chaos Agents")
    _write_recap(tmp_path, 4, "The Chaos Agents were mocked mercilessly this week.\n")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5, weeks_back=3)

    lines = [m["line"] for m in dossier["recap_mentions"]]
    assert any("mocked mercilessly" in line for line in lines)


def test_build_dossier_recap_mentions_no_false_positive_substring(tmp_path):
    """Slug 'fox' must not match an unrelated word containing it as a substring."""
    _write_recap(tmp_path, 4, "The foxtrot dance-off had nothing to do with anyone.\n")

    dossier = gm_dossier.build_dossier(tmp_path, "fox", current_week=5, weeks_back=3)

    assert dossier["recap_mentions"] == []


def test_build_dossier_recap_mentions_capped(tmp_path):
    """recap_mentions never exceeds CAP_RECAP_MENTIONS even with many hits."""
    lines = "\n".join(f"team-chaos did thing {i} this week." for i in range(30))
    _write_recap(tmp_path, 4, lines)

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5, weeks_back=3)

    assert len(dossier["recap_mentions"]) == gm_dossier.CAP_RECAP_MENTIONS == 15


def test_build_dossier_recap_mentions_weeks_back_bounds_window(tmp_path):
    """A mention in a week older than the weeks_back window is excluded."""
    _write_recap(tmp_path, 1, "team-chaos did something notable long ago.\n")
    _write_recap(tmp_path, 5, "team-chaos did something notable recently.\n")

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=6, weeks_back=1)

    lines = [m["line"] for m in dossier["recap_mentions"]]
    assert any("recently" in line for line in lines)
    assert not any("long ago" in line for line in lines)


def test_build_dossier_missing_recap_file_no_crash(tmp_path):
    (tmp_path / "state" / "weeks" / "2026-w04").mkdir(parents=True)  # dir exists, no recap.md

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5)

    assert dossier["recap_mentions"] == []


# ---------------------------------------------------------------------------
# build_dossier -- trajectory
# ---------------------------------------------------------------------------

def test_build_dossier_trajectory_from_standings(tmp_path):
    _write_standings(tmp_path, {
        "team-chaos": {"wins": 3, "losses": 2, "ties": 0, "points_for": 512.4, "points_against": 480.1},
        "team-order": {"wins": 5, "losses": 0, "ties": 0, "points_for": 600.0, "points_against": 300.0},
    })

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert dossier["trajectory"]["record"] == {
        "wins": 3, "losses": 2, "ties": 0, "points_for": 512.4, "points_against": 480.1,
    }


def test_build_dossier_trajectory_recent_results_from_matchups(tmp_path):
    _write_matchups(tmp_path, 4, [
        {"home": "team-chaos", "away": "team-order", "home_score": 110.0, "away_score": 120.0, "winner": "team-order"},
    ])
    _write_matchups(tmp_path, 5, [
        {"home": "team-order", "away": "team-chaos", "home_score": 90.0, "away_score": 130.0, "winner": "team-chaos"},
    ])

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=6, weeks_back=3)

    results = dossier["trajectory"]["recent_results"]
    assert [r["week"] for r in results] == [4, 5]

    week4 = results[0]
    assert week4["opponent"] == "team-order"
    assert week4["result"] == "L"
    assert week4["score"] == 110.0
    assert week4["opponent_score"] == 120.0

    week5 = results[1]
    assert week5["opponent"] == "team-order"
    assert week5["result"] == "W"
    assert week5["score"] == 130.0


def test_build_dossier_trajectory_missing_standings_returns_empty_record(tmp_path):
    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert dossier["trajectory"]["record"] == {}
    assert dossier["trajectory"]["recent_results"] == []


def test_build_dossier_trajectory_unrelated_matchup_not_included(tmp_path):
    """A matchup that doesn't involve this team at all contributes no result."""
    _write_matchups(tmp_path, 4, [
        {"home": "team-order", "away": "team-third", "home_score": 50.0, "away_score": 60.0, "winner": "team-third"},
    ])

    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5, weeks_back=3)

    assert dossier["trajectory"]["recent_results"] == []


# ---------------------------------------------------------------------------
# build_dossier -- shape / robustness
# ---------------------------------------------------------------------------

def test_build_dossier_top_level_shape(tmp_path):
    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", season="2026", current_week=5)

    assert set(dossier.keys()) == {"team", "season", "notes", "own_transactions",
                                    "recap_mentions", "trajectory"}
    assert dossier["team"] == "team-chaos"
    assert dossier["season"] == "2026"
    assert isinstance(dossier["notes"], list)
    assert isinstance(dossier["own_transactions"], list)
    assert isinstance(dossier["recap_mentions"], list)
    assert isinstance(dossier["trajectory"], dict)


def test_build_dossier_completely_empty_repo_never_raises(tmp_path):
    """A totally empty root (no teams/, no state/) -- everything defaults, nothing raises."""
    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos", current_week=5)

    assert dossier["notes"] == []
    assert dossier["own_transactions"] == []
    assert dossier["recap_mentions"] == []
    assert dossier["trajectory"] == {"record": {}, "recent_results": []}


def test_build_dossier_default_current_week_and_weeks_back(tmp_path):
    """Calling with only root+slug (defaults for everything else) doesn't raise
    and returns the well-formed shape."""
    dossier = gm_dossier.build_dossier(tmp_path, "team-chaos")

    assert dossier["team"] == "team-chaos"
    assert dossier["season"] == "2026"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

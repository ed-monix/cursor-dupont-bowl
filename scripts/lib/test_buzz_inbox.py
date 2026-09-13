"""Tests for scripts/buzz_inbox.py — inbox normalizer for the tabloid's X buzz.

Hermetic: tmp_path repos. The invariant under test everywhere: NO path may
raise or block a league run — an empty inbox is a silent no-op, just like
fetch_buzz.py's own skip path.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import buzz_inbox


def _inbox(tmp_path):
    d = buzz_inbox.inbox_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_empty_inbox_is_a_clean_noop(tmp_path):
    _inbox(tmp_path)  # exists but empty

    status, detail = buzz_inbox.normalize_inbox(tmp_path, 3)
    assert status == "empty"
    assert not buzz_inbox.buzz_path(tmp_path, 3).exists()


def test_missing_inbox_dir_is_a_clean_noop(tmp_path):
    # inbox dir not even created
    status, detail = buzz_inbox.normalize_inbox(tmp_path, 3)
    assert status == "empty"


def test_readme_and_gitkeep_are_ignored(tmp_path):
    inbox = _inbox(tmp_path)
    (inbox / "README.md").write_text("# contract\n")
    (inbox / ".gitkeep").write_text("")

    status, _ = buzz_inbox.normalize_inbox(tmp_path, 3)
    assert status == "empty"


def test_existing_canonical_file_is_never_overwritten(tmp_path):
    canonical = buzz_inbox.buzz_path(tmp_path, 4)
    canonical.parent.mkdir(parents=True)
    canonical.write_text("# existing buzz\n- already here\n")

    inbox = _inbox(tmp_path)
    (inbox / "dump.md").write_text("- fresh inbox content\n")

    status, detail = buzz_inbox.normalize_inbox(tmp_path, 4)
    assert status == "canonical-exists"
    # canonical untouched
    assert "already here" in canonical.read_text()
    # inbox file left in place, not consumed
    assert (inbox / "dump.md").exists()


def test_empty_existing_canonical_file_falls_through_to_inbox(tmp_path):
    canonical = buzz_inbox.buzz_path(tmp_path, 4)
    canonical.parent.mkdir(parents=True)
    canonical.write_text("   \n")

    inbox = _inbox(tmp_path)
    (inbox / "dump.md").write_text("- fresh inbox content\n")

    status, _ = buzz_inbox.normalize_inbox(tmp_path, 4)
    assert status == "normalized"
    assert "fresh inbox content" in canonical.read_text()


def test_dropped_file_is_normalized_with_header_and_consumed(tmp_path):
    inbox = _inbox(tmp_path)
    dropped = inbox / "grok-export-2026-09-13.md"
    dropped.write_text("- Puka Nacua hype is out of control. hyped\n")

    status, detail = buzz_inbox.normalize_inbox(tmp_path, 2, season="2026")
    assert status == "normalized"

    canonical = buzz_inbox.buzz_path(tmp_path, 2, season="2026")
    text = canonical.read_text()
    assert "source: inbox" in text
    assert "2026 week 02" in text
    assert "sole source of facts" in text
    assert "Puka Nacua hype" in text

    # consumed file removed from the inbox
    assert not dropped.exists()


def test_most_recently_modified_inbox_file_wins(tmp_path):
    inbox = _inbox(tmp_path)
    older = inbox / "older.md"
    newer = inbox / "newer.md"
    older.write_text("- old storyline\n")
    newer.write_text("- new storyline\n")

    import os
    import time
    now = time.time()
    os.utime(older, (now - 100, now - 100))
    os.utime(newer, (now, now))

    status, _ = buzz_inbox.normalize_inbox(tmp_path, 1)
    assert status == "normalized"
    canonical = buzz_inbox.buzz_path(tmp_path, 1)
    assert "new storyline" in canonical.read_text()
    assert not newer.exists()
    # the file that lost is left alone
    assert older.exists()


def test_dry_run_writes_and_deletes_nothing(tmp_path):
    inbox = _inbox(tmp_path)
    dropped = inbox / "dump.md"
    dropped.write_text("- some buzz\n")

    status, detail = buzz_inbox.normalize_inbox(tmp_path, 1, dry_run=True)
    assert status == "normalized"
    assert "dry run" in detail
    assert not buzz_inbox.buzz_path(tmp_path, 1).exists()
    assert dropped.exists()


def test_txt_extension_is_accepted(tmp_path):
    inbox = _inbox(tmp_path)
    dropped = inbox / "grok.txt"
    dropped.write_text("- a storyline from a txt export\n")

    status, _ = buzz_inbox.normalize_inbox(tmp_path, 9)
    assert status == "normalized"
    assert "a storyline from a txt export" in buzz_inbox.buzz_path(tmp_path, 9).read_text()


def test_unrelated_extensions_are_ignored(tmp_path):
    inbox = _inbox(tmp_path)
    (inbox / "notes.json").write_text("{}")

    status, _ = buzz_inbox.normalize_inbox(tmp_path, 1)
    assert status == "empty"

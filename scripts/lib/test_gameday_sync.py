"""gameday_sync picks the week from the schedule and an Eastern date.

It used to read state/ops/latest.json, which nothing had written since week 2,
so the live stats job synced week 2 for all of week 3 and never captured
Thursday's game. These pin the replacement at the edges that bite: the
Thursday opener, a Sunday, and Monday night — which is Tuesday in UTC.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gameday_sync  # noqa: E402

SCHEDULE = [
    {"week": 2, "date": "2026-09-17", "home": "BUF", "away": "DET", "status": "complete"},
    {"week": 2, "date": "2026-09-20", "home": "ARI", "away": "SEA", "status": "complete"},
    {"week": 2, "date": "2026-09-21", "home": "KC", "away": "DEN", "status": "complete"},
    {"week": 3, "date": "2026-09-24", "home": "GB", "away": "ATL", "status": "complete"},
    {"week": 3, "date": "2026-09-27", "home": "CHI", "away": "MIN", "status": "pre_game"},
    {"week": 3, "date": "2026-09-28", "home": "NYG", "away": "DAL", "status": "pre_game"},
    {"week": 4, "date": "2026-10-01", "home": "NE", "away": "MIA", "status": "pre_game"},
]


def _root(tmp_path, latest_week=2):
    (tmp_path / "state" / "ops").mkdir(parents=True)
    (tmp_path / "state" / "nfl-schedule.json").write_text(json.dumps(SCHEDULE))
    (tmp_path / "state" / "ops" / "latest.json").write_text(
        json.dumps({"week": latest_week, "season": "2026"}))
    return tmp_path


def test_a_stale_latest_json_no_longer_decides_the_week(tmp_path):
    """The bug: latest.json said 2 all through week 3."""
    root = _root(tmp_path, latest_week=2)
    assert gameday_sync.resolve_week(root, today=dt.date(2026, 9, 24)) == 3


def test_thursday_opener_belongs_to_its_own_week(tmp_path):
    assert gameday_sync.resolve_week(_root(tmp_path), today=dt.date(2026, 9, 24)) == 3


def test_sunday_slate(tmp_path):
    assert gameday_sync.resolve_week(_root(tmp_path), today=dt.date(2026, 9, 27)) == 3


def test_monday_night_is_still_this_week(tmp_path):
    """MNF on the Eastern date is week 3. Were we handed Tuesday (the UTC date
    at kickoff) we would roll forward to week 4 mid-game — hence eastern_today."""
    root = _root(tmp_path)
    assert gameday_sync.resolve_week(root, today=dt.date(2026, 9, 28)) == 3
    assert gameday_sync.resolve_week(root, today=dt.date(2026, 9, 29)) == 4


def test_explicit_week_always_wins(tmp_path):
    assert gameday_sync.resolve_week(_root(tmp_path), explicit=7,
                                     today=dt.date(2026, 9, 27)) == 7


def test_without_a_schedule_it_falls_back_to_latest_json(tmp_path):
    root = _root(tmp_path, latest_week=5)
    (root / "state" / "nfl-schedule.json").unlink()
    assert gameday_sync.resolve_week(root, today=dt.date(2026, 9, 27)) == 5


def test_eastern_today_is_not_utc_at_monday_night_kickoff(monkeypatch):
    """00:15 UTC Tuesday is 20:15 Monday in New York."""
    fixed = dt.datetime(2026, 9, 29, 0, 15, tzinfo=dt.timezone.utc)

    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(gameday_sync.dt, "datetime", FakeDT)
    assert gameday_sync.eastern_today() == dt.date(2026, 9, 28)


def test_print_week_is_what_the_commit_label_uses(tmp_path, capsys):
    root = _root(tmp_path)
    rc = gameday_sync.main(["--root", str(root), "--week", "3", "--print-week"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "3"

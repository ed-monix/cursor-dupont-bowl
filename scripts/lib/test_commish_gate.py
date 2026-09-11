"""Commissioner git gate: GMs report in; only valid JSON is written."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from lib.commish_gate import ingest_reply
from lib.daily_ops import ops_for_root, write_ops

REPO = Path(__file__).resolve().parents[2]


def test_write_ops_and_ingest_valid_lineup(tmp_path: Path):
    # Minimal roster so wake_targets works if we copy grok-bots.json
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "grok-bots.json").write_text(
        (REPO / "config" / "grok-bots.json").read_text()
    )
    (tmp_path / "state" / "weeks").mkdir(parents=True)
    call = {
        "action": "lineups-main",
        "today": "2026-09-13",
        "week": 1,
        "wake": {"grok_bots": ["costanza"], "cursor": [], "also": []},
    }
    dest = write_ops(tmp_path, call)
    assert dest.name == "2026-09-13.json"
    latest = json.loads((tmp_path / "state" / "ops" / "latest.json").read_text())
    assert latest["action"] == "lineups-main"

    raw = json.dumps({
        "starters": {"QB": "1", "RB1": "2", "RB2": "3", "WR1": "4",
                     "WR2": "5", "TE": "6", "FLEX": "7", "K": "8", "DEF": "KC"},
        "justification": "I inverted my gut, which is how I know it is wrong.",
    })
    rec = ingest_reply(
        tmp_path, raw=raw, slug="costanza", kind="lineups-main", week=1,
        ops_day="2026-09-13",
    )
    assert rec["ok"] is True
    assert Path(rec["path"]).is_file()
    ops = json.loads((tmp_path / "state" / "ops" / "latest.json").read_text())
    assert "costanza" in ops["gate"]["received"]


def test_ingest_rejects_invalid_and_does_not_write_decision(tmp_path: Path):
    write_ops(tmp_path, {"action": "waivers", "today": "2026-09-08", "week": 1})
    rec = ingest_reply(
        tmp_path,
        raw="I would like a player please",
        slug="costanza",
        kind="waivers",
        week=1,
        ops_day="2026-09-08",
    )
    assert rec["ok"] is False
    assert rec["errors"]
    decisions = tmp_path / "state" / "weeks" / "2026-w01" / "decisions"
    assert not decisions.exists() or not any(decisions.iterdir())
    ops = json.loads((tmp_path / "state" / "ops" / "latest.json").read_text())
    assert "costanza" in ops["gate"]["rejected"]


def test_ops_for_root_still_runs():
    call = ops_for_root(REPO, today=date(2026, 9, 11), season="2026")
    assert call["week"] == 1
    assert "action" in call

"""Tests for scripts/office.py — the end-to-end weekly run, one script.

Hermetic: `subprocess.run` is monkeypatched everywhere except the assertions
that specifically check it was never called. office.py's step-builders never
touch disk to build a plan, so a bare `tmp_path` stands in for the repo root
even though none of the scripts it would shell out to actually live there.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import office  # noqa: E402


class _Recorder:
    """Stands in for subprocess.run; records every call's argv.

    `fail_on`, if set, is the 1-based call number that should come back
    non-zero (everything else succeeds) — enough to test stop-on-error and
    continue-on-error without caring which particular script "failed".
    """

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        rc = 1 if self.fail_on == len(self.calls) else 0
        return subprocess.CompletedProcess(argv, rc)


def _cmd_argvs(steps):
    return [s.argv for s in steps if s.argv is not None]


def _script_names(steps):
    return [pathlib.Path(argv[1]).name for argv in _cmd_argvs(steps)]


# --------------------------------------------------------------------
# build_steps: the ordered plan, per stage (no subprocess involved).
# --------------------------------------------------------------------

def test_waivers_stage_step_order(tmp_path):
    steps = office.build_waivers_steps(tmp_path, 5, "2026")
    assert _script_names(steps) == [
        "sync_sleeper.py", "sync_sleeper.py", "sync_sleeper.py",
        "free_agents.py", "league_board.py", "derive_news.py",
        "buzz_inbox.py", "fetch_buzz.py",
        "gm_pack.py", "agent_turn.py", "gm_pack.py", "gm_turn.py",
        "faab.py", "agent_turn.py", "faab.py", "apply_gate.py",
    ]


def test_waivers_media_before_gm_turns_faab_dry_before_commissioner_before_real(tmp_path):
    argvs = _cmd_argvs(office.build_waivers_steps(tmp_path, 5, "2026"))

    def first(pred):
        return next(i for i, a in enumerate(argvs) if pred(a))

    media_i = first(lambda a: "media" in a)
    turn_i = first(lambda a: pathlib.Path(a[1]).name == "gm_turn.py")
    dry_i = first(lambda a: pathlib.Path(a[1]).name == "faab.py" and "--dry-run" in a)
    commish_i = first(lambda a: "commissioner" in a)
    real_i = first(lambda a: pathlib.Path(a[1]).name == "faab.py" and "--dry-run" not in a)

    assert media_i < turn_i < dry_i < commish_i < real_i


def test_waivers_argv_carries_week_and_season(tmp_path):
    argvs = _cmd_argvs(office.build_waivers_steps(tmp_path, 3, "2027"))
    proj = next(a for a in argvs if "--projections" in a)
    assert "3" in proj
    assert "2027" in proj


def test_lineups_stage_requires_window(tmp_path):
    with pytest.raises(office.OfficeError):
        office.build_steps("lineups", tmp_path, 2, "2026", None)


def test_lineups_stage_step_order(tmp_path):
    steps = office.build_lineups_steps(tmp_path, 2, "2026", "early")
    assert _script_names(steps) == [
        "sync_sleeper.py", "sync_sleeper.py", "sync_sleeper.py",
        "league_board.py", "gm_pack.py", "gm_turn.py", "agent_turn.py",
        "apply_gate.py",
    ]
    for argv in _cmd_argvs(steps):
        if pathlib.Path(argv[1]).name in ("gm_pack.py", "gm_turn.py", "agent_turn.py"):
            assert "early" in argv


def test_lineups_window_main(tmp_path):
    steps = office.build_lineups_steps(tmp_path, 2, "2026", "main")
    for argv in _cmd_argvs(steps):
        if pathlib.Path(argv[1]).name in ("gm_pack.py", "gm_turn.py", "agent_turn.py"):
            assert "main" in argv
            assert "early" not in argv


def test_recap_stage_step_order(tmp_path):
    steps = office.build_recap_steps(tmp_path, 4, "2026")
    assert _script_names(steps) == ["sync_sleeper.py", "score_week.py", "agent_turn.py"]
    argvs = _cmd_argvs(steps)
    assert any("--stats" in a for a in argvs)
    assert any("--final" in a for a in argvs)
    assert any("recap" in a for a in argvs)


def test_build_steps_rejects_unknown_stage(tmp_path):
    with pytest.raises(office.OfficeError):
        office.build_steps("bogus", tmp_path, 1, "2026", None)


# --------------------------------------------------------------------
# --dry-run: print the plan, run nothing.
# --------------------------------------------------------------------

def test_dry_run_calls_no_subprocess(tmp_path, monkeypatch, capsys):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    rc = office.main(["--stage", "waivers", "--week", "5",
                      "--root", str(tmp_path), "--dry-run"])

    assert rc == 0
    assert rec.calls == []
    out = capsys.readouterr().out
    assert "sync_sleeper.py" in out
    assert "week 05: waivers" in out
    assert "(dry-run: no commit)" in out


def test_dry_run_prints_every_step_including_lineups_and_recap(tmp_path, monkeypatch, capsys):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    rc = office.main(["--stage", "lineups", "--week", "2", "--window", "main",
                      "--root", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert rec.calls == []
    out = capsys.readouterr().out
    for name in ("sync_sleeper.py", "league_board.py", "gm_pack.py",
                 "gm_turn.py", "agent_turn.py", "apply_gate.py"):
        assert name in out
    assert "week 02: lineups-main" in out


# --------------------------------------------------------------------
# Failure handling: stop-on-error (default) vs --continue-on-error.
# --------------------------------------------------------------------

def test_failing_step_stops_the_run_and_returns_nonzero(tmp_path, monkeypatch):
    rec = _Recorder(fail_on=2)  # the second sync_sleeper.py call
    monkeypatch.setattr(office.subprocess, "run", rec)

    rc = office.main(["--stage", "waivers", "--week", "5", "--root", str(tmp_path)])

    assert rc != 0
    assert len(rec.calls) == 2  # nothing past the failing step ran
    assert not any(c[0] == "git" for c in rec.calls)  # no commit either


def test_continue_on_error_runs_every_remaining_step(tmp_path, monkeypatch):
    rec = _Recorder(fail_on=2)
    monkeypatch.setattr(office.subprocess, "run", rec)

    rc = office.main([
        "--stage", "waivers", "--week", "5", "--root", str(tmp_path),
        "--continue-on-error",
    ])

    n_cmd_steps = len(_cmd_argvs(office.build_waivers_steps(tmp_path, 5, "2026")))
    assert rc != 0  # the run still failed overall
    assert len(rec.calls) == n_cmd_steps  # but every step still ran
    assert not any(c[0] == "git" for c in rec.calls)  # a failed run never commits


def test_skip_commit_runs_steps_but_never_calls_git(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    rc = office.main(["--stage", "recap", "--week", "1",
                      "--root", str(tmp_path), "--skip-commit"])

    assert rc == 0
    assert rec.calls  # the stage's own steps did run
    assert not any(c[0] == "git" for c in rec.calls)


# --------------------------------------------------------------------
# Commit: message format (with zero-padding) and skip conditions.
# --------------------------------------------------------------------

@pytest.mark.parametrize("stage,window,week,expected", [
    ("waivers", None, 5, "week 05: waivers"),
    ("waivers", None, 12, "week 12: waivers"),
    ("lineups", "early", 3, "week 03: lineups-early"),
    ("lineups", "main", 3, "week 03: lineups-main"),
    ("recap", None, 9, "week 09: recap"),
    ("recap", None, 17, "week 17: recap"),
])
def test_commit_message_format(stage, window, week, expected):
    assert office.commit_message(stage, week, window) == expected


def test_do_commit_skips_under_dry_run(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    ok = office.do_commit(tmp_path, "waivers", 5, "2026", None,
                          dry_run=True, skip_commit=False, steps_ok=True)

    assert ok is True
    assert rec.calls == []


def test_do_commit_skips_under_skip_commit_flag(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    ok = office.do_commit(tmp_path, "waivers", 5, "2026", None,
                          dry_run=False, skip_commit=True, steps_ok=True)

    assert ok is True
    assert rec.calls == []


def test_do_commit_refuses_when_a_step_failed(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    ok = office.do_commit(tmp_path, "waivers", 5, "2026", None,
                          dry_run=False, skip_commit=False, steps_ok=False)

    assert ok is False
    assert rec.calls == []  # never even tries `git add`


def test_do_commit_stages_only_existing_paths_and_commits(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "rulings.md").write_text("# rulings\n")

    ok = office.do_commit(tmp_path, "waivers", 5, "2026", None,
                          dry_run=False, skip_commit=False, steps_ok=True)

    assert ok is True
    add_call = rec.calls[0]
    assert add_call[:3] == ["git", "-C", str(tmp_path)]
    assert "state/rulings.md" in add_call
    assert "teams" not in add_call  # doesn't exist under tmp_path; not staged
    commit_call = rec.calls[1]
    assert commit_call == ["git", "-C", str(tmp_path), "commit", "-m", "week 05: waivers"]


# --------------------------------------------------------------------
# FAAB input prep step: reuses lib.apply_gate, doesn't reimplement it.
# --------------------------------------------------------------------

def test_faab_inputs_step_mirrors_lib_apply_gate(tmp_path):
    decisions = tmp_path / "state" / "weeks" / "2026-w05" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "team-a.json").write_text(json.dumps({
        "claims": [{"add": "p1", "drop": None, "bid": 4}],
        "drops": [], "note_reply": "",
    }))
    standings = tmp_path / "state" / "standings.json"
    standings.write_text(json.dumps({"teams": {
        "team-a": {"wins": 0, "losses": 1, "ties": 0, "points_for": 10},
        "team-b": {"wins": 1, "losses": 0, "ties": 0, "points_for": 20},
    }}))

    steps = office.build_waivers_steps(tmp_path, 5, "2026")
    prep = next(s for s in steps if s.action is not None)
    prep.action()

    wdir = tmp_path / "state" / "weeks" / "2026-w05"
    claims = json.loads((wdir / "claims-from-gate.json").read_text())
    order = json.loads((wdir / "faab-standings-order.json").read_text())
    assert claims == {"team-a": [{"add": "p1", "drop": None, "bid": 4}]}
    assert order == ["team-a", "team-b"]  # worst record first


def test_faab_inputs_step_not_run_under_dry_run(tmp_path, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(office.subprocess, "run", rec)

    office.main(["--stage", "waivers", "--week", "5",
                "--root", str(tmp_path), "--dry-run"])

    assert not (tmp_path / "state" / "weeks" / "2026-w05" / "claims-from-gate.json").exists()


# --------------------------------------------------------------------
# --today: dispatch onto a stage from scripts/daily_ops.py's JSON.
# --------------------------------------------------------------------

def _fake_daily_ops(payload):
    def fake_run(argv, **kwargs):
        if pathlib.Path(argv[1]).name == "daily_ops.py":
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps(payload), stderr="")
        raise AssertionError(f"unexpected subprocess call: {argv}")
    return fake_run


def test_today_idle_action_exits_zero_with_no_further_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(office.subprocess, "run",
                        _fake_daily_ops({"action": "idle", "week": 3, "window": None,
                                         "reason": "slate quiet"}))

    rc = office.main(["--today", "--root", str(tmp_path)])

    assert rc == 0


def test_today_no_week_at_all_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(office.subprocess, "run",
                        _fake_daily_ops({"action": "idle", "week": None}))

    rc = office.main(["--today", "--root", str(tmp_path)])

    assert rc == 0


def test_today_maps_waivers_action_onto_waivers_stage(tmp_path, monkeypatch, capsys):
    def fake_run(argv, **kwargs):
        if pathlib.Path(argv[1]).name == "daily_ops.py":
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=json.dumps({"action": "waivers", "week": 6, "window": None,
                                  "reason": "before kickoff"}),
                stderr="")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(office.subprocess, "run", fake_run)
    rc = office.main(["--today", "--root", str(tmp_path), "--dry-run"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "office: waivers week 06" in out


@pytest.mark.parametrize("action,window,expected_header", [
    ("lineups-early", "early", "lineups week 02 (early)"),
    ("lineups-main", "main", "lineups week 02 (main)"),
])
def test_today_maps_lineup_actions_onto_the_right_window(
        tmp_path, monkeypatch, capsys, action, window, expected_header):
    def fake_run(argv, **kwargs):
        if pathlib.Path(argv[1]).name == "daily_ops.py":
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=json.dumps({"action": action, "week": 2, "window": window,
                                  "reason": "gameday"}),
                stderr="")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(office.subprocess, "run", fake_run)
    rc = office.main(["--today", "--root", str(tmp_path), "--dry-run"])

    assert rc == 0
    assert expected_header in capsys.readouterr().out


def test_today_maps_recap_action(tmp_path, monkeypatch, capsys):
    def fake_run(argv, **kwargs):
        if pathlib.Path(argv[1]).name == "daily_ops.py":
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=json.dumps({"action": "recap", "week": 4, "window": None,
                                  "reason": "slate complete"}),
                stderr="")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(office.subprocess, "run", fake_run)
    rc = office.main(["--today", "--root", str(tmp_path), "--dry-run"])

    assert rc == 0
    assert "office: recap week 04" in capsys.readouterr().out


# --------------------------------------------------------------------
# CLI validation.
# --------------------------------------------------------------------

def test_missing_stage_and_not_today_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit):
        office.main(["--week", "5", "--root", str(tmp_path)])


def test_lineups_without_window_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit):
        office.main(["--stage", "lineups", "--week", "2", "--root", str(tmp_path)])


def test_quiet_step_reduces_a_noisy_success_to_one_line(capsys, tmp_path,
                                                        monkeypatch):
    """gm_pack prints ~100 lines of per-team JSON; the run log should not."""
    import subprocess as sp

    import office

    noisy = "\n".join(f'  "team_{i}": 1234,' for i in range(80)) + "\nwrote 12 packs"

    def fake(argv, **kw):
        return sp.CompletedProcess(argv, 0, stdout=noisy, stderr="")

    monkeypatch.setattr(office.subprocess, "run", fake)
    ok = office.run_step(office.Step("packs", ["x"], quiet=True),
                         root=tmp_path, dry_run=False)
    out = capsys.readouterr().out
    assert ok
    assert "wrote 12 packs" in out
    assert "team_40" not in out          # the blob never reaches the log
    assert len(out.strip().splitlines()) == 2   # the $ line and the ok line


def test_quiet_step_still_shows_everything_when_it_fails(capsys, tmp_path,
                                                         monkeypatch):
    """Quieting a step must not cost you the diagnosis when it breaks."""
    import subprocess as sp

    import office

    def fake(argv, **kw):
        return sp.CompletedProcess(argv, 1, stdout="partial output",
                                   stderr="Traceback: boom")

    monkeypatch.setattr(office.subprocess, "run", fake)
    ok = office.run_step(office.Step("packs", ["x"], quiet=True),
                         root=tmp_path, dry_run=False)
    out = capsys.readouterr().out
    assert not ok
    assert "partial output" in out
    assert "Traceback: boom" in out

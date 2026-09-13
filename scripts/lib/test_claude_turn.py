"""Transport tests for the shared `claude -p` runner.

Two of these guard bugs that actually happened:

  * `--json-schema` takes the schema INLINE. Passing a path made the CLI try to
    parse "/tmp/..." as JSON and every GM turn died in one second.
  * The working directory must contain nothing but the system prompt. That is
    the whole isolation guarantee — if a repo ever leaks into cwd, a GM can
    open another team's files and nobody would notice from the output.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import claude_turn  # noqa: E402


class _Recorder:
    """Stands in for subprocess.run and remembers how it was called."""

    def __init__(self, stdout: str = '{"result": "ok"}', returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.argv = None
        self.cwd = None
        self.cwd_contents = None
        self.stdin = None

    def __call__(self, argv, **kw):
        self.argv = argv
        self.cwd = kw.get("cwd")
        self.stdin = kw.get("input")
        self.cwd_contents = sorted(p.name for p in Path(self.cwd).iterdir())
        return subprocess.CompletedProcess(argv, self.returncode,
                                           stdout=self.stdout, stderr="")


def _run(monkeypatch, rec, **kw):
    monkeypatch.setattr(claude_turn.subprocess, "run", rec)
    params = dict(system_text="SYS", user_text="USER", model="claude-sonnet-5")
    params.update(kw)
    return claude_turn.run_turn(**params)


def test_schema_is_passed_inline_not_as_a_path(monkeypatch):
    rec = _Recorder()
    schema = {"type": "object", "required": ["claims"]}
    _run(monkeypatch, rec, schema=schema)
    i = rec.argv.index("--json-schema")
    assert json.loads(rec.argv[i + 1]) == schema  # inline JSON, not a filename


def test_no_schema_flag_when_none(monkeypatch):
    rec = _Recorder()
    _run(monkeypatch, rec)
    assert "--json-schema" not in rec.argv


def test_working_directory_holds_only_the_system_prompt(monkeypatch):
    """No repo in cwd means no other team's files to open."""
    rec = _Recorder()
    _run(monkeypatch, rec)
    assert rec.cwd_contents == ["system.md"]


def test_temp_directory_is_destroyed_after_the_turn(monkeypatch):
    rec = _Recorder()
    _run(monkeypatch, rec)
    assert not Path(rec.cwd).exists()


def test_private_half_goes_on_stdin(monkeypatch):
    rec = _Recorder()
    _run(monkeypatch, rec, user_text="PRIVATE-PACK")
    assert rec.stdin == "PRIVATE-PACK"


def test_tools_are_denied_and_nothing_waits_on_a_human(monkeypatch):
    rec = _Recorder()
    _run(monkeypatch, rec)
    assert "--permission-mode" in rec.argv
    assert rec.argv[rec.argv.index("--permission-mode") + 1] == "dontAsk"
    assert rec.argv[rec.argv.index("--permission-prompts") + 1] == "none"


def test_model_is_whatever_the_caller_pinned(monkeypatch):
    rec = _Recorder()
    _run(monkeypatch, rec, model="claude-opus-5")
    assert rec.argv[rec.argv.index("--model") + 1] == "claude-opus-5"


def test_nonzero_exit_raises(monkeypatch):
    rec = _Recorder(stdout="", returncode=2)
    with pytest.raises(claude_turn.TurnError):
        _run(monkeypatch, rec)


def test_unparseable_envelope_raises(monkeypatch):
    rec = _Recorder(stdout="not json")
    with pytest.raises(claude_turn.TurnError):
        _run(monkeypatch, rec)


def test_structured_output_wins_over_result_text(monkeypatch):
    rec = _Recorder(stdout=json.dumps(
        {"result": "prose the model also wrote",
         "structured_output": {"claims": []}}))
    out = _run(monkeypatch, rec)
    assert json.loads(out.text) == {"claims": []}


def test_usage_is_extracted_and_accumulated(monkeypatch):
    rec = _Recorder(stdout=json.dumps({
        "result": "ok",
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                  "cache_read_input_tokens": 85, "output_tokens": 3},
    }))
    out = _run(monkeypatch, rec)
    assert out.usage == {"input": 10, "cache_write": 5,
                         "cache_read": 85, "output": 3}
    totals = claude_turn.accumulate({}, out.usage)
    claude_turn.accumulate(totals, out.usage)
    assert totals["cache_read"] == 170
    # 170 cached against 30 fresh
    assert "85% from cache" in claude_turn.usage_line(totals)


def test_usage_line_survives_a_turn_that_reported_nothing():
    assert "0% from cache" in claude_turn.usage_line({})

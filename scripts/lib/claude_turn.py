"""claude_turn.py — one isolated `claude -p` call, shared by every agent turn.

Every model turn in this league runs the same way: a fresh subprocess with cwd
set to an EMPTY temp directory. No repo is mounted, so there is no
`state/players.json`, no `teams/*/opinions.json`, no CLAUDE.md and no skills.
Isolation stops being a rule an agent is asked to follow and becomes a property
of the process — there is nothing to read.

Everything an agent is allowed to know arrives in its prompt:

    system_text   the shared, byte-identical half (cached across sibling turns)
    user_text     the private half, on stdin

That split is not cosmetic. `--append-system-prompt-file` puts the shared half
in the cached prefix, so when twelve GMs run the same slate, the first turn
writes that cache and the other eleven read it.

CLAUDE.md rule 1 note: the commissioner is the only agent that may be handed
other teams' `general-manager.md`. Passing those in `user_text` is the "chat
only" path that rule allows — nothing is written to a shared disk, and the temp
directory is destroyed when the call returns.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional


class TurnError(RuntimeError):
    """The CLI failed, timed out, or returned something unparseable."""


@dataclass
class TurnResult:
    text: str
    usage: dict = field(default_factory=dict)
    envelope: dict = field(default_factory=dict)


def _argv(system_file: pathlib.Path, model: str, schema: Optional[dict]) -> list:
    argv = [
        "claude", "-p",
        "--model", model,
        "--append-system-prompt-file", str(system_file),
        "--output-format", "json",
        # Nothing should ever run a tool in a league turn. The empty cwd makes
        # this moot; deny anything that would prompt and never wait on a human.
        "--permission-mode", "dontAsk",
        "--permission-prompts", "none",
    ]
    if schema is not None:
        # --json-schema takes the schema INLINE, not a path to a file.
        argv += ["--json-schema", json.dumps(schema)]
    return argv


def usage_of(envelope: dict) -> dict:
    u = envelope.get("usage") or {}
    return {
        "input": u.get("input_tokens", 0),
        "cache_write": u.get("cache_creation_input_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "output": u.get("output_tokens", 0),
    }


def answer_text(envelope: dict) -> str:
    structured = envelope.get("structured_output")
    if isinstance(structured, dict) and structured:
        return json.dumps(structured)
    return envelope.get("result") or ""


def run_turn(*, system_text: str, user_text: str, model: str,
             schema: Optional[dict] = None, timeout: int = 600,
             label: str = "turn",
             save_raw: Optional[pathlib.Path] = None) -> TurnResult:
    """Run one turn in an empty directory and return its reply.

    Raises TurnError on a non-zero exit, a timeout, or an envelope that will
    not parse. Callers decide what a failure means — this module never invents
    a fallback, because a fabricated decision is worse than a logged no-op.
    """
    with tempfile.TemporaryDirectory(prefix=f"turn-{label}-") as empty:
        system_file = pathlib.Path(empty) / "system.md"
        system_file.write_text(system_text, encoding="utf-8")
        try:
            proc = subprocess.run(
                _argv(system_file, model, schema),
                input=user_text, capture_output=True, text=True,
                cwd=empty, timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise TurnError(f"{label}: timed out after {timeout}s") from e

        if save_raw is not None:
            save_raw.mkdir(parents=True, exist_ok=True)
            (save_raw / f"{label}.stdout.json").write_text(
                proc.stdout or "", encoding="utf-8")
            if proc.stderr:
                (save_raw / f"{label}.stderr.txt").write_text(
                    proc.stderr, encoding="utf-8")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        raise TurnError(f"{label}: claude exited {proc.returncode}: {detail}")
    try:
        envelope = json.loads(proc.stdout)
    except ValueError as e:
        raise TurnError(f"{label}: could not parse claude envelope: {e}") from e

    return TurnResult(text=answer_text(envelope),
                      usage=usage_of(envelope),
                      envelope=envelope)


def accumulate(totals: dict, usage: dict) -> dict:
    for k in ("input", "cache_write", "cache_read", "output"):
        totals[k] = totals.get(k, 0) + usage.get(k, 0)
    return totals


def usage_line(totals: dict) -> str:
    cached = totals.get("cache_read", 0)
    fresh = totals.get("input", 0) + totals.get("cache_write", 0)
    share = (cached / (cached + fresh) * 100) if (cached + fresh) else 0.0
    return (f"tokens: {fresh:,} fresh + {cached:,} cached ({share:.0f}% from "
            f"cache), {totals.get('output', 0):,} out")

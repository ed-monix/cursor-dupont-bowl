#!/usr/bin/env python3
"""office.py — run a whole weekly league op end to end, no human in the loop.

    python scripts/office.py --stage waivers --week 2
    python scripts/office.py --stage lineups --week 2 --window early
    python scripts/office.py --stage recap   --week 2
    python scripts/office.py --today
    python scripts/office.py --stage waivers --week 2 --dry-run

Today a human runs `.claude/commands/{waivers,lineups,recap}.md` by hand,
one script at a time, off a checklist. This is that checklist turned into
one process, so a scheduler can fire it instead of a person: same scripts,
same order, same one-commit-per-run rule (CLAUDE.md rule 5) — only the
"someone has to type these in order" part changes.

Why a flat ordered step list instead of importing each script's `main`:

  * Every script in this repo already has its own CLI, its own argument
    validation, and its own tests. Importing internals here would mean two
    call paths to keep in sync. A subprocess per step keeps this file a
    dispatcher, not a second implementation.
  * `--dry-run` has to be trustworthy: a human reviewing a flip before it
    touches rosters needs to see the *exact* command that would run, not a
    paraphrase. Building real argv lists and only choosing whether to hand
    them to `subprocess.run` gives that for free.
  * A step that fails should stop the run before it wastes the next one's
    API calls or corrupts the day's commit — hence stop-on-error as the
    default, with `--continue-on-error` as the explicit opt-out.

This script never calls a model itself. `scripts/gm_turn.py` and
`scripts/agent_turn.py` own every `claude -p` invocation; office.py only
decides *when* to run them, on top of the same sync/pack/apply scripts a
human would type by hand.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.apply_gate import (  # noqa: E402
    collect_waiver_claims,
    faab_priority_order,
    week_dir as _apply_gate_week_dir,
)
from lib.trades import apply_accepted, screen_offers  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

STAGES = ("waivers", "lineups", "recap")
WINDOWS = ("early", "main")

# daily_ops.py's action vocabulary (lib/daily_ops.py ACTIONS) mapped onto
# the stage/window this office understands. "idle" and anything unmapped
# mean there is no work today.
TODAY_ACTION_TO_STAGE = {
    "waivers": ("waivers", None),
    "lineups-early": ("lineups", "early"),
    "lineups-main": ("lineups", "main"),
    "recap": ("recap", None),
}


class OfficeError(RuntimeError):
    """A step's plumbing broke before it even got to run a subprocess."""


@dataclass
class Step:
    """One line of the office's checklist.

    A "cmd" step (`argv` set) shells out and its exit code decides success.
    A "note" step (`argv` is None) is everything else: a printed line, plus
    an optional zero-arg `action` for the rare bit of pure-Python plumbing a
    step needs (e.g. materializing the FAAB claims/standings files from
    `decisions/` the way `lib.apply_gate` already does it) — skipped under
    `--dry-run` exactly like a subprocess call is.
    """

    label: str
    argv: Optional[list] = None
    note: Optional[str] = None
    action: Optional[Callable[[], None]] = None
    # A quiet step's stdout is captured and reduced to its last line. gm_pack
    # prints a ~100-line JSON blob of every team's pack sizes, which buries the
    # rest of a run's log. Captured output is printed in full if the step fails,
    # so nothing diagnostic is lost.
    quiet: bool = False


def _py(root: pathlib.Path, script: str, *args) -> list:
    return [PY, str(root / "scripts" / script), *[str(a) for a in args]]


def _ww(week: int) -> str:
    return f"{week:02d}"


def week_dir(root: pathlib.Path, season: str, week: int) -> pathlib.Path:
    return root / "state" / "weeks" / f"{season}-w{_ww(week)}"


def _load_json(path: pathlib.Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def _run_trades(root: pathlib.Path, season: str, week: int) -> None:
    """Screen every outgoing offer, then ask only the targets that survive.

    waivers.md §5: validate in the harness BEFORE spawning the target, because
    week 1 burned ten turns on players who were not where the offerer thought.
    An offer that fails the screen never becomes an agent turn; it is recorded
    with its reason so the commissioner sees why nobody was asked.
    """
    wdir = _apply_gate_week_dir(root, season, week)
    records = screen_offers(root, season, week)
    _write_json(wdir / "trade-screen.json", records)

    if not records:
        print("    no outgoing offers this week")
        return

    passed = [r for r in records if r.get("ok")]
    for rec in records:
        if not rec.get("ok"):
            print(f"    screened out {rec['from']}: {rec.get('reason', '')}")
    print(f"    {len(passed)} of {len(records)} offer(s) go to a target")

    with tempfile.TemporaryDirectory(prefix="office-offers-") as tmp:
        for rec in passed:
            offer = rec["offer"]
            target = offer.get("to_team")
            offer_path = pathlib.Path(tmp) / f"{rec['from']}.json"
            offer_path.write_text(json.dumps(offer), encoding="utf-8")
            argv = _py(root, "gm_turn.py", "--week", week, "--season", season,
                       "--run", "trades", "--team", target,
                       "--offer", offer_path, "--root", root)
            print(f"    $ {shlex.join(argv)}")
            rc = subprocess.run(argv, cwd=str(root)).returncode
            if rc != 0:
                # One unanswered offer is not a reason to lose the whole run's
                # waiver claims. Record it and carry on; the commissioner sees
                # the missing response in trade-screen.json.
                print(f"    trade turn for {target} failed (exit {rc}) — "
                      "recorded, run continues")


def _apply_trades(root: pathlib.Path, season: str, week: int) -> None:
    """Execute accepted offers. Runs after FAAB, which moves rosters first."""
    results = apply_accepted(root, season, week)
    if not results:
        print("    no trade responses to apply")
        return
    for rec in results:
        if rec.get("applied"):
            print(f"    applied {rec.get('from')} <-> {rec['target']}")
        else:
            print(f"    {rec['target']}: {rec.get('reason', '')}")


def _build_faab_inputs(root: pathlib.Path, season: str, week: int) -> None:
    """Write claims-from-gate.json + faab-standings-order.json into the week
    folder — the same two files scripts/apply_gate.py's apply_waivers()
    builds before it calls faab.py. Reused here (not reimplemented) so both
    call paths agree on what "the claims" and "the tiebreak order" mean."""
    wdir = _apply_gate_week_dir(root, season, week)
    claims = collect_waiver_claims(wdir / "decisions")
    # standings.json does not exist until week 1 has been scored, and faab.py
    # raises on a contested claim whose team is missing from the order — which
    # is exactly what killed the first automated week-2 run. Ruling 2026-02
    # covers it: reversed draft order until standings exist, then the normal
    # tiebreak "takes over automatically".
    order, basis = faab_priority_order(root, season)
    _write_json(wdir / "claims-from-gate.json", claims)
    _write_json(wdir / "faab-standings-order.json", order)
    print(f"    FAAB tiebreak basis: {basis} ({len(order)} teams)")


# --------------------------------------------------------------------------
# Stage step builders — mirror .claude/commands/{waivers,lineups,recap}.md.
# --------------------------------------------------------------------------

def build_waivers_steps(root: pathlib.Path, week: int, season: str) -> list:
    wdir = week_dir(root, season, week)
    claims_path = wdir / "claims-from-gate.json"
    order_path = wdir / "faab-standings-order.json"
    faab_report = ["--report-out", str(wdir / "faab-report.json")]

    return [
        Step("sync players", _py(root, "sync_sleeper.py", "--players")),
        Step("sync projections",
             _py(root, "sync_sleeper.py", "--projections", "--week", week,
                 "--season", season)),
        Step("sync NFL schedule",
             _py(root, "sync_sleeper.py", "--schedule", "--week", week,
                 "--season", season)),
        Step("free agent pool",
             _py(root, "free_agents.py", "--week", week, "--season", season)),
        Step("league board",
             _py(root, "league_board.py", "--week", week, "--season", season)),
        Step("derive news facts",
             _py(root, "derive_news.py", "--week", week, "--season", season)),
        Step("promote inbox buzz (Grok automation drop)",
             _py(root, "buzz_inbox.py", "--week", week, "--season", season,
                 "--root", root)),
        Step("fetch buzz (owner file / xAI / skip)",
             _py(root, "fetch_buzz.py", "--week", week, "--season", season)),
        Step("build GM packs (pre-tabloid)",
             _py(root, "gm_pack.py", "--week", week, "--season", season,
                 "--run", "waivers", "--root", root), quiet=True),
        Step("media turn — Kris writes the tabloid",
             _py(root, "agent_turn.py", "--role", "media", "--week", week,
                 "--season", season, "--root", root)),
        Step("rebuild GM packs (so GMs see the tabloid)",
             _py(root, "gm_pack.py", "--week", week, "--season", season,
                 "--run", "waivers", "--root", root), quiet=True),
        Step("12 GM turns — waiver decisions",
             _py(root, "gm_turn.py", "--week", week, "--season", season,
                 "--run", "waivers", "--root", root)),
        Step("build FAAB inputs from decisions/ + standings.json",
             note=f"writes {claims_path} and {order_path} (mirrors "
                  "lib.apply_gate's own construction)",
             action=lambda: _build_faab_inputs(root, season, week)),
        Step("FAAB dry run (for commissioner review)",
             _py(root, "faab.py", "--claims", claims_path,
                 "--standings", order_path, *faab_report, "--dry-run")),
        Step("trades — screen offers, ask only valid targets",
             note="validates each outgoing offer against both rosters, then "
                  "runs gm_turn --run trades for the targets that survive; "
                  "writes trade-screen.json",
             action=lambda: _run_trades(root, season, week)),
        Step("commissioner review — waivers",
             _py(root, "agent_turn.py", "--role", "commissioner", "--week", week,
                 "--season", season, "--stage", "waivers", "--root", root)),
        Step("FAAB apply (real)",
             _py(root, "faab.py", "--claims", claims_path,
                 "--standings", order_path, *faab_report)),
        # Explicit stage/week: apply_gate otherwise takes both from
        # state/ops/latest.json, which is whatever the last daily_ops --write
        # decided. A run driven by --stage/--week must not inherit that.
        Step("apply accepted trades",
             note="executes every accepted offer on both rosters and logs it "
                  "to transactions.jsonl; counters are recorded, never "
                  "auto-applied",
             action=lambda: _apply_trades(root, season, week)),
        Step("apply gate (Cloud Agent apply)",
             _py(root, "apply_gate.py", "--root", root,
                 "--action", "waivers", "--week", week, "--season", season)),
    ]


def build_lineups_steps(root: pathlib.Path, week: int, season: str,
                        window: str) -> list:
    return [
        Step("sync players", _py(root, "sync_sleeper.py", "--players")),
        Step("sync projections",
             _py(root, "sync_sleeper.py", "--projections", "--week", week,
                 "--season", season)),
        Step("sync NFL schedule",
             _py(root, "sync_sleeper.py", "--schedule", "--week", week,
                 "--season", season)),
        Step("league board",
             _py(root, "league_board.py", "--week", week, "--season", season)),
        Step(f"build GM packs — lineups/{window}",
             _py(root, "gm_pack.py", "--week", week, "--season", season,
                 "--run", "lineups", "--window", window, "--root", root)),
        Step(f"12 GM turns — lineups/{window}",
             _py(root, "gm_turn.py", "--week", week, "--season", season,
                 "--run", "lineups", "--window", window, "--root", root),
             quiet=True),
        Step(f"commissioner review — lineups/{window}",
             _py(root, "agent_turn.py", "--role", "commissioner", "--week", week,
                 "--season", season, "--stage", "lineups", "--window", window,
                 "--root", root)),
        Step("apply gate (freeze + merge + fallback)",
             _py(root, "apply_gate.py", "--root", root,
                 "--action", f"lineups-{window}", "--week", week,
                 "--season", season, "--window", window)),
    ]


def build_recap_steps(root: pathlib.Path, week: int, season: str) -> list:
    return [
        Step("sync final stats",
             _py(root, "sync_sleeper.py", "--stats", "--week", week,
                 "--season", season)),
        Step("score the week officially",
             _py(root, "score_week.py", "--week", week, "--season", season,
                 "--final")),
        Step("commissioner writes the recap",
             _py(root, "agent_turn.py", "--role", "commissioner", "--week", week,
                 "--season", season, "--stage", "recap", "--root", root)),
    ]


def build_steps(stage: str, root: pathlib.Path, week: int, season: str,
                window: Optional[str] = None) -> list:
    if stage == "waivers":
        return build_waivers_steps(root, week, season)
    if stage == "lineups":
        if window not in WINDOWS:
            raise OfficeError(f"lineups stage needs --window early|main, got {window!r}")
        return build_lineups_steps(root, week, season, window)
    if stage == "recap":
        return build_recap_steps(root, week, season)
    raise OfficeError(f"unknown stage {stage!r}")


# --------------------------------------------------------------------------
# Commit — CLAUDE.md rule 5: exactly one commit per run.
# --------------------------------------------------------------------------

def commit_label(stage: str, window: Optional[str]) -> str:
    if stage == "lineups":
        return f"lineups-{window}"
    return stage


def commit_message(stage: str, week: int, window: Optional[str]) -> str:
    return f"week {_ww(week)}: {commit_label(stage, window)}"


def commit_paths(stage: str, root: pathlib.Path, season: str, week: int,
                 window: Optional[str] = None) -> list:
    """Paths to `git add` before the run's one commit, per the relevant
    command doc's own staging list (waivers.md §7, recap.md §4). lineups.md
    doesn't enumerate one explicitly, so this mirrors what the window step
    actually writes: rosters, the week folder, that week's forum thread."""
    wdir = f"state/weeks/{season}-w{_ww(week)}"
    if stage == "waivers":
        return [
            "teams",  # rosters + press
            "state/transactions.jsonl",
            "state/free-agents.json",
            "state/league-board.json",
            "state/news",  # tabloid + buzz
            wdir,  # news-facts, faab-report, packs, decisions
            f"state/forum/{season}-w{_ww(week)}.jsonl",
            "state/rulings.md",
        ]
    if stage == "lineups":
        return [
            "teams",  # roster.json starters + press
            wdir,  # lineups.json, decisions
            f"state/forum/{season}-w{_ww(week)}.jsonl",
        ]
    if stage == "recap":
        return [
            "state/standings.json",
            f"{wdir}/matchups.json",
            f"{wdir}/recap.md",
        ]
    raise OfficeError(f"unknown stage {stage!r}")


def do_commit(root: pathlib.Path, stage: str, week: int, season: str,
             window: Optional[str], *, dry_run: bool, skip_commit: bool,
             steps_ok: bool) -> bool:
    message = commit_message(stage, week, window)
    paths = commit_paths(stage, root, season, week, window)
    add_argv = ["git", "-C", str(root), "add", "--", *paths]
    commit_argv = ["git", "-C", str(root), "commit", "-m", message]

    print(f"[commit] {message}")
    print("    $ " + shlex.join(add_argv))
    print("    $ " + shlex.join(commit_argv))

    if dry_run:
        print("    (dry-run: no commit)")
        return True
    if skip_commit:
        print("    (--skip-commit: no commit)")
        return True
    if not steps_ok:
        print("    (a step failed this run: no commit)")
        return False

    existing = [p for p in paths if (root / p).exists()]
    if not existing:
        print("    nothing to stage; skipping commit")
        return True

    rc = subprocess.run(["git", "-C", str(root), "add", "--", *existing]).returncode
    if rc != 0:
        print(f"    git add failed (exit {rc})")
        return False
    rc = subprocess.run(commit_argv).returncode
    if rc != 0:
        print(f"    git commit failed (exit {rc}) — possibly nothing staged")
        return False
    print("    committed")
    return True


# --------------------------------------------------------------------------
# Running a stage.
# --------------------------------------------------------------------------

def run_step(step: Step, *, root: pathlib.Path, dry_run: bool) -> bool:
    if step.argv is not None:
        print("    $ " + shlex.join(step.argv))
        if dry_run:
            return True
        if step.quiet:
            proc = subprocess.run(step.argv, cwd=str(root),
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"    FAILED (exit {proc.returncode})")
                for stream in (proc.stdout, proc.stderr):
                    if stream:
                        print("    " + stream.strip().replace("\n", "\n    "))
                return False
            tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
            print(f"    ok{' — ' + tail[-1].strip() if tail else ''}"[:160])
            return True
        proc = subprocess.run(step.argv, cwd=str(root))
        if proc.returncode != 0:
            print(f"    FAILED (exit {proc.returncode})")
            return False
        print("    ok")
        return True

    if step.note:
        print(f"    note: {step.note}")
    if dry_run:
        print("    (dry-run: not executed)")
        return True
    if step.action is not None:
        try:
            step.action()
        except Exception as e:  # surface any prep failure as a failed step
            print(f"    FAILED: {e}")
            return False
    print("    ok")
    return True


def run_stage(stage: str, root: pathlib.Path, week: int, season: str,
             window: Optional[str], *, dry_run: bool, skip_commit: bool,
             stop_on_error: bool) -> int:
    steps = build_steps(stage, root, week, season, window)
    header = f"=== office: {stage} week {_ww(week)}"
    if window:
        header += f" ({window})"
    header += f" — season {season} ==="
    print(header)

    ok = True
    for i, step in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {step.label}")
        if not run_step(step, root=root, dry_run=dry_run):
            ok = False
            if stop_on_error:
                remaining = len(steps) - i
                if remaining:
                    print(f"stopping: {remaining} step(s) not run "
                          f"(pass --continue-on-error to run them anyway)")
                break

    commit_ok = do_commit(root, stage, week, season, window, dry_run=dry_run,
                          skip_commit=skip_commit, steps_ok=ok)
    return 0 if (ok and commit_ok) else 1


# --------------------------------------------------------------------------
# --today.
# --------------------------------------------------------------------------

def resolve_today(root: pathlib.Path, season: str) -> dict:
    """Ask scripts/daily_ops.py what today's op is. Read-only (it inspects
    the synced NFL slate and this week's done-flags, writes nothing) so it
    always actually runs, --dry-run included — there is no plan to print
    before we know which stage it names."""
    argv = _py(root, "daily_ops.py", "--root", root, "--season", season)
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(root))
    if proc.returncode != 0:
        raise OfficeError(
            f"daily_ops.py exited {proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")
    try:
        return json.loads(proc.stdout)
    except ValueError as e:
        raise OfficeError(f"could not parse daily_ops.py output: {e}") from e


def stage_from_today(ops: dict):
    """(stage, week, window) from a daily_ops.py call, or None for no work."""
    action = ops.get("action")
    week = ops.get("week")
    if not week or action in (None, "idle"):
        return None
    mapped = TODAY_ACTION_TO_STAGE.get(action)
    if mapped is None:
        return None
    stage, window = mapped
    return stage, week, window


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Run a whole DuPont Bowl weekly op end to end.")
    ap.add_argument("--stage", choices=STAGES,
                    help="waivers | lineups | recap (required unless --today)")
    ap.add_argument("--week", type=int, help="week number")
    ap.add_argument("--window", choices=WINDOWS,
                    help="required for --stage lineups")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--today", action="store_true",
                    help="pick the stage from scripts/daily_ops.py")
    ap.add_argument("--dry-run", action="store_true",
                    help="print every step's exact argv; run nothing")
    ap.add_argument("--skip-commit", action="store_true",
                    help="run every step but do not make the one commit")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--stop-on-error", dest="stop_on_error", action="store_true",
                    default=True,
                    help="(default) stop at the first failing step")
    ap.add_argument("--continue-on-error", dest="stop_on_error",
                    action="store_false",
                    help="keep running remaining steps after a failure")
    return ap


def main(argv=None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)

    if args.today:
        ops = resolve_today(root, args.season)
        print(f"today: action={ops.get('action')} week={ops.get('week')} "
              f"window={ops.get('window')} — {ops.get('reason', '')}")
        resolved = stage_from_today(ops)
        if resolved is None:
            print("today: no work to do")
            return 0
        stage, week, window = resolved
    else:
        if not args.stage:
            ap.error("--stage is required unless --today is given")
        if not args.week:
            ap.error("--week is required")
        stage = args.stage
        week = args.week
        window = args.window
        if stage == "lineups" and window is None:
            ap.error("--window early|main is required for --stage lineups")

    try:
        return run_stage(stage, root, week, args.season, window,
                         dry_run=args.dry_run, skip_commit=args.skip_commit,
                         stop_on_error=args.stop_on_error)
    except OfficeError as e:
        print(f"office: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

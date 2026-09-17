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
import time
from dataclasses import dataclass
from typing import Callable, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib.apply_gate import (  # noqa: E402
    collect_waiver_claims,
    faab_priority_order,
    week_dir as _apply_gate_week_dir,
)
from lib.trades import apply_accepted, screen_offers  # noqa: E402
from lib.reconcile import reconcile  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from forum import append_post  # noqa: E402
from gm_dossier import append_press  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

# Files sync_sleeper.py rewrites in place on any stage that syncs. Staging them
# is not bookkeeping: `--push` rebases before pushing and rebase refuses on a
# dirty tree, so a synced-but-unstaged file fails the push of a week that
# otherwise succeeded -- which is how week 2's waivers landed locally and went
# nowhere. They are also the evidence the run decided against. b3d78d4 fixed
# this for the recap's stats.json; these are the same bug on the other stages.
SYNCED_STATE = (
    "state/players.json",
    "state/nfl-schedule.json",
)

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


def _decisions(root: pathlib.Path, season: str, week: int, pattern: str) -> dict:
    """{slug: decision} for one run's decision files.

    `<slug>.json`, `<slug>.lineup-<w>.json` and `<slug>.trade.json` all reduce
    to the same slug, so a bare `*.json` glob would let the trade response
    clobber the waiver decision. Exclude the other two by name, exactly as
    lib.apply_gate.collect_waiver_claims does.
    """
    wdir = _apply_gate_week_dir(root, season, week) / "decisions"
    out = {}
    if not wdir.is_dir():
        return out
    bare = pattern == "*.json"
    for path in sorted(wdir.glob(pattern)):
        name = path.name
        if bare and (".lineup-" in name or name.endswith(".trade.json")):
            continue
        slug = name.split(".")[0]
        try:
            out[slug] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def _post_forum(root: pathlib.Path, season: str, week: int,
                run: str, window: Optional[str] = None) -> None:
    """Append every GM's forum_post to the week's thread.

    The office staged state/forum/<week>.jsonl for commit from the start but
    nothing ever wrote it, so an automated week committed an empty thread. The
    forum is not decoration: it feeds Kris's tabloid, the commissioner's Quote
    of the Week, and the public half of next week's GM packs. Without it the
    whole trash-talk loop is dead and the league gets quieter every week.
    """
    pattern = "*.json" if run == "waivers" else f"*.lineup-{window or 'main'}.json"
    posted = 0
    for slug, decision in _decisions(root, season, week, pattern).items():
        if not isinstance(decision, dict):
            continue
        post = decision.get("forum_post")
        if not isinstance(post, str) or not post.strip():
            continue
        try:
            append_post(root, week, slug, post.strip(), season)
            posted += 1
        except ValueError:
            # One post per team per run; a re-run is not a second post.
            pass
    print(f"    {posted} forum post(s)")


def _press(root: pathlib.Path, season: str, week: int,
           stage: str, window: Optional[str] = None) -> None:
    """Append each GM's own words plus the outcome to teams/<slug>/press/.

    waivers.md §6 and lineups.md §3 both call for this. It is the substrate
    build_dossier reads back, so skipping it means every GM's memory stops
    accumulating and the personalities flatten out over a season.
    """
    wdir = _apply_gate_week_dir(root, season, week)
    wrote = 0
    if stage == "waivers":
        report = _load_json(wdir / "faab-report.json", {}) or {}
        outcomes: dict = {}
        for claim in report.get("claims") or []:
            outcomes.setdefault(claim.get("team"), []).append(
                f"- `{claim.get('add')}` — **{claim.get('status')}**: "
                f"{claim.get('reason', '')}")
        for slug, decision in _decisions(root, season, week, "*.json").items():
            if not isinstance(decision, dict):
                continue
            blocks = []
            note = (decision.get("note_reply") or "").strip()
            if note:
                blocks.append(f"**On the owner's note:** {note}")
            if outcomes.get(slug):
                blocks.append("**Waivers:**\n" + "\n".join(outcomes[slug]))
            if blocks:
                append_press(root, slug, week, "\n\n".join(blocks), season)
                wrote += 1
    else:
        lineups = _load_json(wdir / "lineups.json", {}) or {}
        pattern = f"*.lineup-{window or 'main'}.json"
        for slug, decision in _decisions(root, season, week, pattern).items():
            just = (decision.get("justification") or "").strip()
            fell_back = bool((lineups.get(slug) or {}).get("fallback"))
            blocks = []
            if just:
                blocks.append(f"**Lineup ({window or 'main'}):** {just}")
            if fell_back:
                blocks.append("**Lineup fell back — Hall of Shame.**")
            if blocks:
                append_press(root, slug, week, "\n\n".join(blocks), season)
                wrote += 1
    print(f"    press appended for {wrote} team(s)")


def _reconcile(root: pathlib.Path, season: str, week: int) -> None:
    """Write live-vs-final drift for the recap, when live scores were captured.

    recap.md §2: the live scoreboard is entertainment, the Monday finals are
    official, and the commissioner gets to mock the gap. scoreboard.py writes
    live-scores.json only while it is running, so its absence is a normal week,
    not an error — the doc says to skip and say so.
    """
    wdir = _apply_gate_week_dir(root, season, week)
    live = _load_json(wdir / "live-scores.json", None)
    if not live:
        print("    no live scores captured this week — nothing to reconcile")
        return
    final = _load_json(wdir / "matchups.json", {}) or {}
    finals = final.get("player_scores") or final.get("final_scores") or {}
    if not finals:
        print("    no final per-player scores in matchups.json — skipped")
        return
    drift = reconcile(live, finals)
    _write_json(wdir / "reconciliation.json", drift)
    print(f"    {len(drift)} player(s) drifted live -> final")


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
        Step("forum — post the week's trash talk",
             note="appends each GM's forum_post to state/forum/<week>.jsonl; "
                  "feeds the tabloid, Quote of the Week, and next week's packs",
             action=lambda: _post_forum(root, season, week, "waivers")),
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
        # apply_gate.apply_waivers() IS the real FAAB apply: it collects the
        # claims, builds the tiebreak order and runs faab.py with
        # --transactions. Running faab.py separately here as well applied
        # everything twice — harmless on the rosters, because the second pass
        # found every drop "already gone", but it overwrote faab-report.json
        # with eight claims marked `skipped` that had in fact been applied, and
        # the press then quoted that wrong record back at the GMs.
        #
        # Explicit stage/week: apply_gate otherwise takes both from
        # state/ops/latest.json, which is whatever the last daily_ops --write
        # decided. A run driven by --stage/--week must not inherit that.
        Step("apply gate (the real FAAB apply)",
             _py(root, "apply_gate.py", "--root", root,
                 "--action", "waivers", "--week", week, "--season", season)),
        # After the apply, not before: FAAB moves rosters, and a trade that was
        # legal at screening time may not be legal once it has.
        Step("apply accepted trades",
             note="executes every accepted offer on both rosters and logs it "
                  "to transactions.jsonl; counters are recorded, never "
                  "auto-applied",
             action=lambda: _apply_trades(root, season, week)),
        Step("press — each GM's own words plus the outcome",
             note="appends to teams/<slug>/press/; this is the substrate "
                  "build_dossier reads back into next week's GM pack",
             action=lambda: _press(root, season, week, "waivers")),
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
        Step("forum — post the week's trash talk",
             note="appends each GM's forum_post from this window's lineups",
             action=lambda: _post_forum(root, season, week, "lineups", window)),
        Step(f"commissioner review — lineups/{window}",
             _py(root, "agent_turn.py", "--role", "commissioner", "--week", week,
                 "--season", season, "--stage", "lineups", "--window", window,
                 "--root", root)),
        Step("apply gate (freeze + merge + fallback)",
             _py(root, "apply_gate.py", "--root", root,
                 "--action", f"lineups-{window}", "--week", week,
                 "--season", season, "--window", window)),
        Step("press — lineup justifications and any fallback",
             note="appends to teams/<slug>/press/",
             action=lambda: _press(root, season, week, "lineups", window)),
    ]


def build_recap_steps(root: pathlib.Path, week: int, season: str) -> list:
    return [
        Step("sync final stats",
             _py(root, "sync_sleeper.py", "--stats", "--week", week,
                 "--season", season)),
        Step("score the week officially",
             _py(root, "score_week.py", "--week", week, "--season", season,
                 "--final")),
        Step("reconcile live vs final",
             note="writes reconciliation.json when the live scoreboard "
                  "captured scores; a week with none is normal",
             action=lambda: _reconcile(root, season, week)),
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
            *SYNCED_STATE,
        ]
    if stage == "lineups":
        return [
            "teams",  # roster.json starters + press
            wdir,  # lineups.json, decisions
            f"state/forum/{season}-w{_ww(week)}.jsonl",
            # This stage syncs and rebuilds the board too, so it carries the
            # same staging debt waivers did.
            "state/league-board.json",
            *SYNCED_STATE,
        ]
    if stage == "recap":
        return [
            "state/standings.json",
            f"{wdir}/matchups.json",
            f"{wdir}/recap.md",
            # recap.md §4 lists only the three above, but step 1 re-syncs the
            # final stats and step 2 scores the week from them. Leaving them
            # uncommitted means the evidence for the official result is not in
            # the repo, and the dirty tree blocks the rebase the push needs.
            f"{wdir}/stats.json",
        ]
    raise OfficeError(f"unknown stage {stage!r}")


def do_commit(root: pathlib.Path, stage: str, week: int, season: str,
             window: Optional[str], *, dry_run: bool, skip_commit: bool,
             steps_ok: bool, push: bool = False) -> bool:
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

    # Every command doc ends with "Viewer: push to main. GitHub Pages rebuilds
    # the board" — viewer.yml triggers on push, so without this the board goes
    # stale even though the run succeeded. Off by default: a scheduled office
    # can turn it on, and nothing pushes by accident until someone does.
    if push:
        return _push_with_rebase(root)
    return True


def _push_with_rebase(root: pathlib.Path, attempts: int = 4) -> bool:
    """Push, integrating whatever landed while the run was working.

    viewer.yml pushes a board rebuild after every push to main, so by the time
    a run that takes minutes reaches its push, the remote has almost always
    moved. A bare `git push` loses that race — it did on the very first live
    run, leaving week 1 committed locally and unpushed.

    Fetch, rebase, push; retry with backoff. The rebase is safe because the
    run's own work is already committed and every stage stages everything it
    wrote (see commit_paths) — nothing of ours is left in the working tree to
    block it.
    """
    for attempt in range(1, attempts + 1):
        subprocess.run(["git", "-C", str(root), "fetch", "--quiet", "origin"])
        rebase = subprocess.run(
            ["git", "-C", str(root), "pull", "--quiet", "--rebase"])
        if rebase.returncode != 0:
            print(f"    rebase failed (exit {rebase.returncode}) — "
                  "resolve by hand, the run's commit is safe locally")
            return False
        push = subprocess.run(["git", "-C", str(root), "push", "--quiet"])
        if push.returncode == 0:
            print("    pushed — viewer.yml will rebuild the board")
            return True
        print(f"    push attempt {attempt}/{attempts} lost a race; retrying")
        time.sleep(2 ** attempt)
    print("    could not push after retries — the run's commit is safe locally")
    return False


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
            # The last line of a JSON blob is "}", which summarises nothing.
            # Take the last line that carries actual words.
            tail = [ln.strip() for ln in (proc.stdout or "").splitlines()
                    if ln.strip(" \t{}[],\"")]
            print(f"    ok{' — ' + tail[-1] if tail else ''}"[:160])
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
             stop_on_error: bool, push: bool = False) -> int:
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
                          skip_commit=skip_commit, steps_ok=ok, push=push)
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
    ap.add_argument("--push", action="store_true",
                    help="push after the commit so GitHub Pages rebuilds the "
                         "board (each command doc's final 'Viewer' step); off "
                         "by default")
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
                         stop_on_error=args.stop_on_error, push=args.push)
    except OfficeError as e:
        print(f"office: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

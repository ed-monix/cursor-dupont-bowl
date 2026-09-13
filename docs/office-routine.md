# The office routine — under evaluation, not switched on

This describes a path to a hands-off weekly run: a scheduled Claude Code
session that drives the league instead of an owner typing slash commands.
None of it is live yet. See "Not yet switched on" below before assuming any
of this fires on its own.

## The host

The host is a scheduled Claude Code session running in Anthropic's cloud
remote environment (`cloud_default`). It is already authenticated on the
owner's Claude subscription the same way any other Claude Code Remote
session in that environment is — there is no separate API key, no
`claude setup-token`, and no GitHub secret to create for this path. Do not
add one.

That session needs the same things any run of this repo needs: the repo
checked out, `requirements.txt` installed, and the usual hard rules from
`CLAUDE.md` followed (isolation, notes are pressure, scripts decide facts,
everything logged, one commit per run, commissioner reviews before apply).

## The single entrypoint: `scripts/office.py`

The plan is one script that a scheduled session can call with no other
argument than the stage and the week:

```
python scripts/office.py --stage waivers|lineups|recap --week N
```

**`scripts/office.py` is being written in parallel by another worker and may
not exist on disk yet.** Its documented job — per the task that spawned this
file — is to run the whole sequence for a stage in one shot: syncs
(`sync_sleeper.py`, `free_agents.py`, `league_board.py`, `derive_news.py`,
buzz), the tabloid pass, all 12 GM turns, FAAB (and trades where applicable),
the commissioner review, applying the result, and then exactly one commit —
folding together the steps that `/waivers`, `/lineups`, and `/recap`
currently walk through by hand (see `.claude/commands/waivers.md`,
`.claude/commands/lineups.md`, and `.claude/commands/recap.md`). Treat the
flag names
above as the interface contract to build toward, not as confirmed behavior
of code that has been read and verified — verify against the actual script
once it lands before relying on it.

## What this does NOT take over

**Live in-game scoring stays exactly where it is:** `.github/workflows/
gameday.yml`, on GitHub Actions cron, unrelated to any Claude Code session.
Its actual schedule (cron is UTC):

- `*/20 0-3 * * 5` — Thursday night football window (Thu 8pm–11pm ET, which
  is Fri 00:00–03:59 UTC)
- `*/20 16-23 * * 0` — the Sunday slate (Sun 12pm–7pm ET / Sun 16:00–23:59
  UTC)
- `*/20 0-4 * * 1` — late Sunday into Monday night (Sun 8pm ET–Mon 12am ET /
  Mon 00:00–04:59 UTC)

plus a manual `workflow_dispatch`. Each run calls `scripts/gameday_sync.py`
and commits stat changes straight to `main` as `github-actions[bot]`.

**`viewer.yml` rebuilds the board on every push to `main`** (excluding
pushes that only touch `index.html` / `.nojekyll`, to avoid rebuilding its
own commit), running `scripts/build_viewer.py` and committing the rebuilt
`index.html` back to `main`. GitHub Pages serves that file directly
("Deploy from a branch" → `main` → `/`).

The office routine, if and when it runs, produces the same kind of commits
`/waivers` / `/lineups` / `/recap` already produce today — `viewer.yml` picks
those up exactly as it does now. Nothing about gameday scoring or the board
rebuild changes.

## How a daily routine would know what to do

`scripts/daily_ops.py` already exists and already answers "what does today
need" from the public NFL slate — no GM files involved. Run as:

```
python scripts/daily_ops.py [--date YYYY-MM-DD] [--season 2026] [--write]
```

it prints one JSON object to stdout: `action` (one of `idle`, `waivers`,
`lineups-early`, `lineups-main`, `recap`), `window` (`early`/`main`/`null`),
`week`, `season`, `today`, `first_kickoff`, `games_today`, `done` (which of
this week's stages are already recorded), `wake` (who the Commissioner would
ping — Grok Bot slugs, Cursor-owned slugs, or others, empty for `idle`), and
`reason` (a one-line human explanation of the call). `--write` additionally
persists that call to `state/ops/<date>.json` and `state/ops/latest.json`.

This is exactly the shape a daily-firing routine needs: fire once a day,
read `action`, and exit immediately with no further work on an `idle` day.
It decides purely from `state/weeks/*/nfl-games.json` and each week's done
flags (`faab-report.json`, `lineups.json` windows, `recap.md`) — it does not
touch GM files.

## One commit per run

CLAUDE.md rule 5 is unconditional: **one commit per run**, message
`week NN: waivers|lineups-early|lineups-main|recap|notes` (or `draft`). A
week may have two lineup commits (early + main) — never more than one per
invocation of a stage. Any office-routine build has to preserve this exactly;
it is not a detail `scripts/office.py` gets to relax.

## Known gap: a commissioner block is not enforced

Found by the first end-to-end week-2 run. The commissioner reviewed the FAAB
dry run, correctly blocked one claim as illegal (a team dropping its starting
DEF with a full bench), and closed with "the run may proceed, with
patricia-moyer's claim struck".

**Nothing implements "struck."** `office.py` writes the signoff to a file and
moves to the next step; the real FAAB run then hits the same illegal claim and
`lib/rosters.apply_transaction` raises. The scripts caught it independently —
CLAUDE.md rule 3 held, legality came from the script and not from trusting the
agent — so the outcome is safe: stop-on-error, no commit, league state
unchanged. But it is not hands-off. One GM's illegal claim stalls the week
until a person looks at it.

In the human flow this never surfaced, because the operator reads the signoff
and strikes the claim before applying. There is no operator in the office.

Three ways out, none of them chosen yet — this is a league-rules decision, not
a plumbing one:

1. `faab.py` marks such a claim `skipped` (a status it already has, with
   reasons) instead of raising. Self-healing; a GM's illegal claim dies quietly.
2. The commissioner returns structured JSON alongside its markdown, and
   `office.py` strikes what it blocks. Faithful to the design, more moving parts.
3. Leave it. Halting on illegal input is defensible; the office is then
   autonomous only for weeks where every GM files a legal claim.

Until one is picked, a scheduled run can fail on the waivers stage and will
correctly commit nothing when it does.

## Not yet switched on

This document describes an evaluation path, not a running system:

- `scripts/office.py` now exists and has been run end to end. The waivers
  stage halts on the gap above; the lineups stage completed clean (12 of 12
  lineups validated, no fallbacks, one commit).
- No Routine, cron, or GitHub Actions workflow currently calls
  `scripts/office.py`, `scripts/daily_ops.py`, or any wrapper around them on
  a schedule. Nothing in `.github/workflows/` or elsewhere fires this
  routine today.
- The GM-turn step it would depend on (`scripts/gm_turn.py`, one isolated
  `claude -p` per team) is itself still under test — see the "Under test:
  one-command GM turns" sections of `.claude/commands/waivers.md` and
  `.claude/commands/lineups.md`. The legacy Grok Bot gateway
  (`scripts/grok_bots.py dispatch`) remains the documented default until a
  full week has run clean on the new path.
- Turning this on is a decision for the owner, not something this document
  authorizes. When it happens, expect it to show up as an explicit
  Routine/cron entry plus an update to this file — not a silent addition.

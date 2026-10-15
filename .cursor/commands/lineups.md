---
description: Lock starting lineups for one NFL window (early = Tue–Sat games; main = Sun/Mon + leftover)
argument-hint: <week> <early|main>
---

# /lineups — lineup window, week $ARGUMENTS

Locks starters for **one NFL window**, not "Sunday." Season 2026.

Parse `$ARGUMENTS` as `<week> <window>` where window is `early` or `main`.
Ask if empty.

- **early** — run before Thursday (and any Wed/Fri/Sat) kickoffs. Only
  slots whose NFL game is Tue–Sat become frozen. Sunday/Monday starters
  may still change later.
- **main** — run before the Sunday slate (and after late injury news).
  Frozen early slots stay frozen. Remaining slots (Sun/Mon, plus anyone
  the early run missed) lock. MNF is set here.

A GM always submits a **full** legal lineup. Scripts merge it:
`scripts/lib/lineup_windows.merge_lineup`. Moving a frozen slot is a
validation error (retry once), then keep the locked player. Games that
have already kicked (`in_game` / `complete`) are frozen even if a window
was skipped.

No in-game swaps. Owners still have no lever except notes.

Same hard rules as always. Inline packs, tools off — **never**
`state/players.json`. Injury/BYE flags live on the pack's `my_board`
rows (`status`, `injury`, `window`, `kicked`).

## 1. Injury + slate sync

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week <WW>
python scripts/sync_sleeper.py --schedule --week <WW>
python scripts/league_board.py --week <WW>
python scripts/gm_pack.py --week <WW> --run lineups --window <early|main>
```

## 2. GM lineups (all 12 through `gm_turn.py`)

```bash
python scripts/gm_turn.py --week <WW> --run lineups --window <W>
```

The default since 2026-10-15, for all 12 teams, the owned two (`your-team`,
`wifes-team`) included: no Cursor, no awake laptop. Each team runs as an
isolated `claude -p` call on Sonnet with an empty working directory, so
there is no repo mounted and no other team's files to open. Turn one fires
alone to warm the shared cache prefix before the other eleven fan out, so no
GM sees another's lineup by construction rather than by convention. Replies
follow `docs/schemas/sunday-lineup.json` into
`decisions/<slug>.lineup-<W>.json`. Beliefs first; projections are an
opinion. `--dry-run` sizes the prompts without calling. If the `claude` CLI
is missing or cannot authenticate, stop: do not answer for the GMs. The
daily `bowl_league_ops` routine (`routines/bowl_league_ops.md`) runs this
command when the ops call is `lineups-early` or `lineups-main`.

### Optional: the Grok Bot gateway

Only while Nick's local Grok gateway is running (a cloud routine cannot
reach it), the celebrity GMs can answer as Grok Bots instead:

```bash
python scripts/grok_bots.py dispatch --week <WW> --kind lineups --window <W>
```

The owned two still go through `gm_turn.py --team <slug>`, off the shared
Bot disk.

Validate schema + `validate_lineup`. BYE/Out starters must be acknowledged
in the justification. Retry once. Then the **script** applies the window
(freeze, merge, fallback) — do not hand-merge:

```bash
python scripts/lineups.py --week <WW> --window <early|main> \
  --decisions-dir state/weeks/2026-w<WW>/decisions
```

`--dry-run` first for commissioner review. Fallback = `best_legal_lineup`
with frozen slots held (do not bench a locked Thursday starter). Logged
`fallback: true` only when the submitted lineup was illegal or missing.

Writes `state/weeks/2026-w<WW>/lineups.json` (includes `locked_slots`,
`windows_run`, `justifications`) and updates `roster.json` starters.
Also keep a copy of each validated GM object at
`state/weeks/2026-w<WW>/decisions/<slug>.lineup-<window>.json`.

Forum optional via `forum.append_post` (one post per team per run).

## 3. Commissioner + freeze

Commissioner (`agents/commissioner.md`) confirms every lineup is legal and
fallbacks are recorded, in its own isolated turn, which writes
`state/weeks/2026-w<WW>/commissioner-signoff-<window>.md`:

```bash
python scripts/agent_turn.py --role commissioner --week <WW> --stage lineups --window <early|main>
```

Does not second-guess a legal benching of a stud. Persist starters into
`roster.json` for slots that locked this window (leave still-unlocked
slots as the current declaration). `append_press` the justification.

## 4. Commit (exactly one)

`week <WW>: lineups-early` or `week <WW>: lineups-main`

A week may have **two** lineup commits. That is the point.

## 5. Viewer

Push to `main`. GitHub Pages rebuilds the board. Optional local preview:
`python scripts/build_viewer.py --season 2026`.

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

## 2. GM lineups (12 packs)

Each team: paste
`python scripts/gm_pack.py --week <WW> --team <slug> --run lineups --window <W> --prompt`
and require `docs/schemas/sunday-lineup.json` (filename kept; this is the
lineup schema). Beliefs first; projections are an opinion.

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

Commissioner confirms every lineup is legal and fallbacks are recorded.
Does not second-guess a legal benching of a stud. Persist starters into
`roster.json` for slots that locked this window (leave still-unlocked
slots as the current declaration). `append_press` the justification.

## 4. Commit (exactly one)

`week <WW>: lineups-early` or `week <WW>: lineups-main`

A week may have **two** lineup commits. That is the point.

## 5. Viewer

`python scripts/build_viewer.py --season 2026`. Artifact republish via
`/refresh-board` if this session has the tool.

---
description: Run the draft — 15-round snake, AI GMs pick in character, humans pick live (--mock for all-AI)
argument-hint: [--mock]
---

# /draft — the DuPont Bowl draft $ARGUMENTS

Runs the one-time preseason draft (PLAN.md §6). 12 teams, 15-round snake, 180
picks. If `$ARGUMENTS` contains `--mock`, run ALL 12 teams as AI with NO human
pauses (the dress-rehearsal mode from TASKS.md 3.2) — otherwise `your-team` and
`wifes-team` pick via live human input. Hard rules still apply, above all
**isolation**: a picking agent sees ONLY its own `general-manager.md`.

## 1. Build the board

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week 1
```

Board = all skill players + K/DEF with projected points
(`scripts/lib/scoring.score_player` over each projection row) and Sleeper ADP
(the `adp_*` fields in `projections.json`), sorted best-first. A player leaves
the board the instant it is drafted — the board is the single source of "who is
still available."

## 2. Draft order + schedule

Randomize the 12-team order (announce the seed used, for reproducibility) and
build the snake: round 1 in order, round 2 reversed, alternating for 15 rounds.
Generate the season schedule from the drafted order now:

```bash
python scripts/schedule.py <team slugs in draft order> --seed <seed> --out state/schedule.json
```

## 3. Make the picks (live)

For each of the 180 picks in snake order:

- **AI pick** (always, in `--mock`; for AI teams otherwise): spawn ONE subagent
  with ONLY that team's `general-manager.md`, its roster so far, and the current
  board. It returns its pick (a `player_id` that must still be on the board) plus
  ONE line of in-character commentary. Print the pick and the line live.
- **Human pick** (non-mock, human teams): PAUSE, prompt for a player name,
  resolve it to a board player_id, confirm.

Validate EVERY pick before accepting it (`scripts/lib/rosters`): the player must
be on the board (never drafted twice — reject and re-prompt/re-ask on a dupe),
and the resulting roster must stay legal, including the draft cap of **one K and
one DEF max** (league-rules "Draft"). A pick that can't be placed legally is
rejected with the reason; the agent/human picks again. Append every pick to
`state/draft-log.jsonl`: `{pick_no, round, team, player_id, name, pos, commentary}`.

## 4. Finalize

- Write every team's `teams/<slug>/roster.json` from its drafted players (fill
  the standard starters where sensible; the rest to bench). Each must pass
  `validate_roster`.
- Confirm `state/schedule.json` and `state/draft-log.jsonl` are written.
- Spawn the Commissioner (`agents/commissioner.md`) to write a **draft-grades
  column** — one grade + barb per team, in its dry voice, guaranteed unfair
  (PLAN.md §6). Save it to `state/draft-grades.md`.

## 5. Commit (exactly one)

Stage all rosters, `state/schedule.json`, `state/draft-log.jsonl`,
`state/draft-grades.md`; ONE commit: `draft` (or `draft (mock)` for `--mock`).

## Dress-rehearsal requirement

Before the real draft, a full 15-round `--mock` must complete clean: all 180
picks placed, no player drafted twice, every roster validates (TASKS.md 3.2 AC).

---
description: Run the draft — 15-round snake, all 12 GMs pick in character while the owners watch (--mock for the dress rehearsal)
argument-hint: [--mock]
---

# /draft — the DuPont Bowl draft $ARGUMENTS

Runs the one-time preseason draft (PLAN.md §6). 12 teams, 15-round snake, 180
picks — **every pick is made by that team's GM agent**, the owners' two teams
included; the humans watch their GMs draft for them. `--mock` in `$ARGUMENTS`
is the dress rehearsal (TASKS.md 3.2): identical flow, committed as a mock.
Hard rules still apply, above all **isolation**: a picking agent sees ONLY
its own `general-manager.md`. If `teams/your-team` or `teams/wifes-team`'s
GM file still carries its PLACEHOLDER banner, STOP and ask the owner for the
persona before drafting.

## 1. Build the board

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week 1
```

Board = all skill players + K/DEF, **ranked by Sleeper ADP** — the `adp_dd_ppr`
field in `projections.json`, ascending (lowest ADP = best available first). ADP
is the draft-realistic order; do NOT sort the board by projected points.
Single-week projected points badly over-rank QBs (a Week-1 points sort puts ~10
QBs in the top 15), so points are shown **alongside** each player for context —
half-PPR via `scripts/lib/scoring.score_player` over the projection row — but
ADP is the sort key. Players with no `adp_dd_ppr` fall to the bottom (undrafted
depth). A player leaves the board the instant it is drafted — the board is the
single source of "who is still available."

## 2. Draft order + schedule

Randomize the 12-team order (announce the seed used, for reproducibility) and
build the snake: round 1 in order, round 2 reversed, alternating for 15 rounds.
Generate the season schedule from the drafted order now:

```bash
python scripts/schedule.py <team slugs in draft order> --seed <seed> --out state/schedule.json
```

## 3. Make the picks (live)

For each of the 180 picks in snake order:

- **Every pick, every team**: spawn ONE subagent with ONLY that team's
  `general-manager.md`, its roster so far, and the public context below.
  Isolation still holds: the log is public record, never another team's GM
  file. It returns its pick (a `player_id` that must still be on the board)
  plus ONE line of in-character commentary (25 words max). Print both live.
  There are no human picks — the owners' GMs draft for them.

**Token diet (required — the full board is ~3,000 players and 180 picks will
burn millions of tokens without it):**

- **Inline-only subagents — this is the big one.** The ORCHESTRATOR builds
  the dieted context below and pastes it into the subagent's prompt as text.
  The subagent's instructions must say: everything you need is in this
  prompt; do NOT read files, run commands, or use tools; reply with ONLY the
  pick JSON + one line. A pick agent that Reads `state/players.json` or
  `projections.json` itself reloads the full pool into its own window and
  defeats the entire diet (~50K+/pick observed when this happens).
- **Wishlist mode for rounds 9–15 (one spawn per GM, not per pick):** at the
  top of round 9, spawn all 12 GMs in parallel; each gets its roster,
  remaining needs, and a top-80 board slice, and returns a RANKED list of
  ~25 targets for its remaining picks with one line of commentary per
  target. Fill rounds 9–15 in snake order from the wishlists — highest-ranked
  still-available name, validator on every pick as usual; re-spawn a GM only
  when its list runs dry or a pick is rejected. 12 spawns instead of 84; the
  per-target lines still print live.

- **Board slice, never the full pool:** the top 60 available by projected
  points PLUS the top 12 available at each of QB/RB/WR/TE and top 3 K/DEF
  (name, pos, NFL team, proj only). No GM ever picks outside that slice; if
  one insists on a name not in it, resolve the name against the full board
  in the harness, not by widening the context.
- **Draft log slice:** the last 24 picks verbatim (two rounds of reactions,
  runs, and spite material) plus a one-line per-team summary of position
  counts drafted so far — never the full log.
- **Opinions:** full `opinions.json` for rounds 1–3 (rivalries shape the
  early board); from round 4 on, a compact one-line stance map
  (`team: stance`) instead.
- **Rounds 11–15, accelerated:** board slice trimmed to the top 40 relevant,
  no draft log — just the per-team position-counts summary.

Validate EVERY pick before accepting it (`scripts/lib/rosters`): the player must
be on the board (never drafted twice — reject and re-prompt/re-ask on a dupe),
and the resulting roster must stay legal, including the draft cap of **one K and
one DEF max** (league-rules "Draft"). A pick that can't be placed legally is
rejected with the reason; the agent picks again. Append every pick to
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

Then (real draft only, not `--mock`): build `web/viewer.html`
(`python scripts/build_viewer.py --season 2026`) and republish the artifact in
place per `.claude/commands/refresh-board.md` step 4 — the league's first look
at the board should be draft night. If this session lacks the Artifact tool,
say so and tell the owner to run `/refresh-board`.

## Dress-rehearsal requirement

Before the real draft, a full 15-round `--mock` must complete clean: all 180
picks placed, no player drafted twice, every roster validates (TASKS.md 3.2 AC).

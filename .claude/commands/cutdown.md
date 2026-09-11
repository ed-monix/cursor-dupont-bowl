---
description: One-time pre-week-1 transaction period — league-office cleanup, a double trade window, and a full waiver run so all 12 teams are set for kickoff
argument-hint: (no arguments — runs once, before week 1)
---

# /cutdown — the league office gets everyone in order

A ONE-TIME transaction period between the draft and the week-1 games. Purpose
(owner directive): clear the draft's dead weight, unwind positional
overloads through trades, and run a full waiver cycle so every team fields a
startable week-1 lineup. All hard rules apply (isolation, scripts decide
facts, everything logged, commissioner review, one commit).

## 1. Fix the facts first (scripts decide facts)

```bash
python scripts/sync_sleeper.py --players     # re-trim: now excludes teamless/retired players
python scripts/sync_sleeper.py --projections --week 1
python scripts/free_agents.py  --week 1
python scripts/league_board.py --week 1
```

The refreshed `state/players.json` no longer contains players without an NFL
team (the Le'Veon Bell class — a draft-board data bug, not a GM decision).

## 2. League-office corrections (commissioner, mechanical)

For every roster, list rostered player ids NOT present in the refreshed
`state/players.json`. These were drafted off an erroneous board — a facts
bug, so the fix is the league office's, not the GMs': release each via
`rosters.apply_transaction` (drop), log each to `state/transactions.jsonl`
with `reasoning: "league-office correction: player not on an NFL roster"`,
and record ONE ruling in `state/rulings.md` (dry voice; this is the
commissioner's favorite kind of ruling — nobody's fault, everybody's
paperwork). No FAAB is charged or refunded.

## 3. The commissioner's memo

Spawn the Commissioner (`agents/commissioner.md`) with the league board and
each team's post-correction roster. It writes
`state/weeks/2026-w01/commissioner-memo.md` — short, procedural, weary:

- the corrections applied (who lost whom, and why),
- each team's roster imbalances stated as FACTS (e.g. "six wide receivers,
  one running back, no tight end" — script-derived counts, no strategy
  advice; the commissioner does not coach),
- the window's special provisions (below) and the deadline: all claims and
  trades resolve before Wednesday's kickoff,
- a closing reminder that a team unable to field a legal lineup Sunday gets
  the fallback lineup and a Hall of Shame citation, "which the league office
  will regret typing, but will type."

The memo joins every GM's context this run (public record).

## 4. GM decisions — with a DOUBLE trade window

Run the standard Saturday machinery (per `.claude/commands/saturday.md`
steps 3–6: isolated subagent per team with dossier + memo + free agents +
league board; decisions.py; retry-then-no-claims fallback) with two
one-window-only exceptions, recorded in `state/rulings.md`:

- **Two outgoing trade offers per team** this window (normal cap: one). The
  memo says why: the league office would like the roster imbalances to be
  the GMs' problem, briefly, rather than the season's problem, permanently.
- **Waiver priority applies draft order reversed** (no standings exist yet):
  last pick of round 1 = best claim on FAAB ties.

Trades still resolve accept/reject/counter as always; chaos is legal;
lopsided is flagged, never blocked. FAAB comes out of the normal $100 —
this window is not free money.

## 5. Commissioner review, apply, verify startable

Commissioner reviews everything (blocks rule violations only), then apply
via `faab.py` (no `--dry-run`) and `apply_transaction` for trades. Then the
startability check, per team: every starter slot fillable by a rostered,
position-eligible player with an NFL team (`validate_lineup` against a
best-effort fill). Any team that fails gets listed in the run output for
the owner — with this window's pool that should be nobody.

## 6. Commit (exactly one) + refresh the board

Stage rosters, `state/transactions.jsonl`, `state/players.json`,
`state/free-agents.json`, `state/league-board.json`, the memo, the FAAB
report, and the ruling; ONE commit: `week 01: cutdown`. Then push to `main`
so GitHub Pages rebuilds the board.

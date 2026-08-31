---
description: Sunday lineup run — every team locks a legal starting lineup before kickoff
argument-hint: <week number, e.g. 5>
---

# /sunday — lineup run, week $ARGUMENTS

Locks starting lineups (PLAN.md §4 Sunday). Season 2026; `WW` = zero-padded week
from `$ARGUMENTS` (ask if empty). Same hard rules as always (isolation, notes
are pressure, scripts decide facts, everything logged, one commit, commissioner
reviews). Lineups freeze at the end of this run — no in-day swaps for anyone,
including humans (league-rules "Weekly deadlines").

## 1. Final injury / inactives sync

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week <WW>
```

This refreshes each player's `status`/`injury` and the week's projections
(needed for the fallback lineup).

## 2. AI team lineups (one isolated subagent per team)

For each AI team, spawn ONE subagent whose context is ONLY its own
`general-manager.md`, its `roster.json`, the refreshed `state/players.json`
(so it sees injury/BYE/Out flags), and its next opponent. It replies with a
single JSON object matching `docs/schemas/sunday-lineup.json`:
`{starters: {slot: player_id}, justification: "<one paragraph, in character>"}`.

Validate each with `scripts/lib/decisions.parse_and_validate` against the schema,
then with `scripts/lib/rosters.validate_lineup(roster, players)` — every starter
slot filled, position-eligible, no player started twice. Also flag any starter
whose `status`/`injury` is BYE or Out: the lineup is legal but the GM must have
acknowledged it in its justification; if not, treat as a validation failure for
the retry.

**On failure: retry once** with the specific errors. If it still fails, set the
**fallback lineup** deterministically and log `fallback: true` (public shame in
the recap):

```python
from lib.rosters import best_legal_lineup   # highest-projected legal lineup
```

Build it from the team's rostered pool + this week's projections + scoring, then
`validate_lineup` it. Quote each GM's justification verbatim into the log.

## 3. Human team lineups

For `your-team` and `wifes-team`, PAUSE and prompt the human to set each lineup;
run it through the same `validate_lineup` and the same freeze deadline.

## 4. Commissioner review + freeze

Spawn the Commissioner (`agents/commissioner.md`) to confirm every lineup is
legal and every `fallback: true` is recorded. It blocks only illegal lineups
(after the retry+fallback path already ran); it does not second-guess a legal
benching of a stud — chaos is legal. Persist each team's locked starters into its
`roster.json` and write the full set of lineups + justifications + fallback flags
to `state/weeks/2026-w<WW>/lineups.json`.

## 5. Commit (exactly one)

Stage updated rosters and the lineups file; ONE commit: `week <WW>: sunday`.

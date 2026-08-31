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

For each AI team, spawn ONE subagent whose context is ONLY its own material +
public record — Sunday is the run people watch, so give it something to REACT to
(R2), not just a projection column:

- its `teams/<slug>/general-manager.md` (NEVER another team's) and `roster.json`,
- the refreshed `state/players.json` (so it sees injury/BYE/Out flags),
- its **dossier** (`gm_dossier.build_dossier(root, slug, current_week=<WW>)`),
- **this week's owner note** and **its own Saturday `note_reply`**,
- **last week's box score** (`state/weeks/2026-w<PREV>/matchups.json`) and
  current `state/standings.json`,
- this week's **tabloid** (`state/news/2026-w<WW>.md`) and the **forum thread**
  (`forum.read_thread`),
- its next opponent from `state/schedule.json`.

**Beliefs first (R7).** Have the agent state its in-character read of the matchup
FIRST (reacting to the tabloid, the note, the forum, the opponent, last week's
wound), THEN set the lineup consistent with that read. Frame projections as *"the
analytics department's opinion"* — trusted, discounted, or resented per the GM's
Gut & Media-Diet sections; never "start the highest projection."

It replies with one JSON object matching `docs/schemas/sunday-lineup.json`:
`{starters: {slot: player_id}, justification: "<one paragraph, in character>",
forum_post?}`. Append any `forum_post` via `forum.append_post(root, <WW>, slug, post)`.

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
to `state/weeks/2026-w<WW>/lineups.json`. Append each GM's justification (and a
`fallback: true` note where it applies) to `teams/<slug>/press/2026-w<WW>.md` via
`gm_dossier.append_press(...)` — the recap and next week's dossier read it back.

## 5. Commit (exactly one)

Stage updated rosters, `state/weeks/2026-w<WW>/lineups.json`,
`state/forum/2026-w<WW>.jsonl`, and updated `teams/*/press/`; ONE commit:
`week <WW>: sunday`.

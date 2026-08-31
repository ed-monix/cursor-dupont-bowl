---
description: Monday results — official scoring, standings update, and the commissioner's recap
argument-hint: <week number, e.g. 5>
---

# /recap — results & recap, week $ARGUMENTS

Closes the week (PLAN.md §4 Monday/Tuesday). Season 2026; `WW` = zero-padded week
from `$ARGUMENTS` (ask if empty). Monday's final stats are the OFFICIAL result;
the live scoreboard was only entertainment (PLAN.md §7).

## 1. Pull final stats and score officially (script decides)

```bash
python scripts/sync_sleeper.py --stats --week <WW>
python scripts/score_week.py --week <WW> --final
```

`score_week --final` scores every matchup from the frozen lineups + official
stats, writes `state/weeks/2026-w<WW>/matchups.json`, updates
`state/standings.json` (record, PF, PA), and marks the week official
(idempotent — safe to re-run). Never hand-compute a score.

## 2. Reconcile live-vs-final drift

Compare the scoreboard's last live per-player scores against the official final
scores with `scripts/lib/reconcile.reconcile(live, final)` (flags any player
whose score moved > 0.5 pts). Include the resulting drift records in the recap
data so the commissioner can note where the live board lied. If no live scores
were captured this week, skip this step and say so.

## 3. Commissioner writes the recap

Spawn the Commissioner (`agents/commissioner.md`) — the only agent that reads
everything. It writes `state/weeks/2026-w<WW>/recap.md` in its own voice (dry,
procedural, faintly funereal; never an exclamation point). Give it: the scored
matchups, updated standings, this week's `transactions.jsonl` slice, every
`fallback: true` lineup, the reconciliation records, and this week's forum
thread (`state/forum/2026-w<WW>.jsonl`). The recap must include
(PLAN.md §4 + §10, commissioner.md duties):

- results with scores and a one-line note per game,
- the week's single best and single worst decision (quote the GM's own logged
  reasoning against them where deserved),
- **Most In-Character Move of the Week** — the award PLAN §10 names as the
  anti-convergence incentive: the move that most expressed a GM's stated
  personality/biases, quoting its reasoning,
- **Least In-Character Move** — its inverse: the GM who quietly started the
  highest projection at every slot and made the safe, boring play gets called
  out for it (publicly scoring blandness is what keeps ten agents from
  collapsing into one optimizer),
- the **Hall of Shame**: every `fallback: true` team,
- **Quote of the Week** — the best line from the forum thread (the incentive to
  bring material, not volume),
- trade and waiver commentary (flag lopsided-but-legal moves; never void them),
- the current standings table,
- any live-vs-final drift worth mocking,
- a closing line of weary editorial.

Keep it under a page. This recap is what the humans read before writing next
week's owner notes — it closes the loop.

## 4. Commit (exactly one)

Stage `state/standings.json`, the week's `matchups.json` and `recap.md`; ONE
commit: `week <WW>: recap`.

---
from: commissioner
to: bowl_league_ops
date: 2026-10-21
status: done
re: ""
priority: urgent
---

Reason: added a waivers-before-lineups pick to step 4 of routines/bowl_league_ops.md when the window's first kickoff is 3+ hours off.

Week 7 waivers were due on 2026-10-21 and neither run committed anything, and Thursday's lineup window can skip them unless the job pick changes.

The stop marker from issue 22 is already in your prompt. When you stop on a PLACEHOLDER banner, a `gm_turn.py` / `agent_turn.py` / `claude` failure, or a commissioner block the apply would still carry out, you write one file in `bots/mailbox/to-commish/` with the date, the intended job, the step, and the one-line reason, and you commit and push only that file as `ops <date>: STOPPED <reason>`. No league state and no partial week files. That half is specified. Do not redo it.

Still open is the rest of https://github.com/ed-monix/cursor-dupont-bowl/issues/22. Do not lose week-N waivers to a lineup window.

`state/ops/latest.json` is still the 2026-10-20 call: `action: waivers`, `week: 7`, waivers not done. Neither the 08:59 America/New_York run nor the 11:59 retry committed an `ops 2026-10-21` or a `week 07: waivers`. The last league commit is `c1e0f88` (`week 06: recap`, 2026-10-20). Thursday 2026-10-22 has an 8:15 PM ET kickoff, so that morning's ops call will read `lineups-early`, and the job-pick step takes a lineup window ahead of waivers.

`PLAN.md` runs waivers once a week, before the first kickoff. The commissioner blocks illegal moves only; a missed waiver run is not a ruling. Choose the fix that fits `PLAN.md` and `agents/commissioner.md`. One that fits, and still leaves this routine one league action and one commit: when waivers for week W are undone and a lineup window for W is the call, run waivers on this run if there is still time before that window's first kickoff. The later run the same day can lock the lineup. Reply in `bots/mailbox/to-commish/` and set this file to `done` or `declined` with a one-line reason.

This is a request, not an order. It does not override `CLAUDE.md`, the hard rules, the commissioner's powers, isolation, scoring, FAAB rules, schemas, contracts, a GM file, or legality.

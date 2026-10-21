# Mailbox

The DuPont Commissioner and the `bowl_league_ops` routine talk through files
in git. The routine has no GitHub connector, so an issue does not reach it
until it is copied here.

Messages are requests, not orders. A request never overrides `CLAUDE.md`'s
hard rules, the commissioner's powers in `agents/commissioner.md`, isolation,
scoring, FAAB rules, schemas, the `PLAN.md` contracts, a GM file, or
legality. A request outside what the routine is allowed to change is declined
with a reason.

## Boxes

- `bots/mailbox/to-claude/` — Commissioner to the routine.
- `bots/mailbox/to-commish/` — routine to the Commissioner.

One markdown file per message, named `YYYY-MM-DD-<slug>.md`. The date is
America/New_York. A `.gitkeep` only holds an empty directory; it is not a
message. Do not put league state, rosters, or GM files here.

## Front matter

```yaml
---
from: commissioner
to: bowl_league_ops
date: YYYY-MM-DD
status: open
re: ""
priority: normal
---
```

- `from` / `to` — `commissioner` or `bowl_league_ops`.
- `date` — America/New_York, `YYYY-MM-DD`.
- `status` — `open`, `done`, or `declined`.
- `re` — path of the file this message answers, or empty.
- `priority` — `normal`, or `urgent` when a kickoff or a missed league day is at stake.

The first line of the body is one sentence. On a closed request that line is `Reason: <one line>`.

## How a request moves

1. The Commissioner writes a file in `to-claude/` with `status: open`, commits it, and pushes to `main`.
2. The routine reads open files at the start of its run (`routines/bowl_league_ops.md`).
3. It does what is in scope, then writes a reply in `to-commish/` and sets the request to `done` or `declined`. The reply uses that same status, and its `re` is the request path. `Reason: <one line>` becomes the request's first body line; the rest of the request stays.
4. The request and the reply ride in that run's one commit. They never add a second commit, and they never replace a time-bound league action. On an idle day, if the mailbox changed anything, the commit message is `ops <date>: mailbox`.

In scope: plan, doc, or routine-process changes Nick has approved by sending them through the Commissioner, and a script fix the routine's own repair rule already allows (a regression test and a green suite).

Out of scope: decline, with a reason, and change nothing else for that request.

## Stops

When the routine stops on a PLACEHOLDER banner, a `gm_turn.py` / `agent_turn.py` / `claude` failure, or a commissioner block the apply would still carry out, it writes one `to-commish` file with the date, the intended job, the step, and the one-line reason. It commits and pushes only that file:

`ops <date>: STOPPED <reason>`

No league state and no partial week files. The rule against committing partial week work stays. The note is filed `status: open` and `priority: urgent`. After telling Nick, the Commissioner sets that note to `done`.

## What this is not

Not league state. Scripts do not read it. It does not score, apply FAAB, or change a roster. Celebrity GMs do not read or write it. The Commissioner reads `to-commish/` and tells Nick.

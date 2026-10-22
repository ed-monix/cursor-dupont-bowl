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
2. That push kicks off the routine: `.github/workflows/mailbox-kickoff.yml` fires `bowl_league_ops` through its API trigger. If the trigger is not set up, the next scheduled run (08:59 or 11:59 America/New_York) picks it up. The routine reads open files at the start of its run (`routines/bowl_league_ops.md`).
3. It does what is in scope, then writes a reply in `to-commish/` and sets the request to `done` or `declined`. The reply uses that same status, and its `re` is the request path. `Reason: <one line>` becomes the request's first body line; the rest of the request stays.
4. The request and the reply ride in that run's one commit. They never add a second commit, and they never replace a time-bound league action. On an idle day, if the mailbox changed anything, the commit message is `ops <date>: mailbox`.

In scope: plan, doc, or routine-process changes Nick has approved by sending them through the Commissioner, and a script fix the routine's own repair rule already allows (a regression test and a green suite).

Out of scope: decline, with a reason, and change nothing else for that request.

## Kicking off a run

The Commissioner starts a run in one of two ways:

- **With a request:** push a `to-claude/` file with `status: open`. The workflow fires the routine with the file names. The routine reads the files on `main`; the fire text is only a pointer.
- **Without a request:** run the `Mailbox kickoff` workflow by hand (Actions tab, `workflow_dispatch`, optional reason). Use it when a league day was missed and nothing needs saying.

A kicked-off run is an ordinary run: it takes today's ops call, does at most one league action, and makes one commit. The done flags keep it from repeating a job a scheduled run already finished. The routine's own replies set requests to `done` or `declined`, so they never fire it again. The API trigger allows 30 fires per hour.

Setup, once, by Nick: on claude.ai/code/routines, edit `bowl_league_ops`, Trigger -> + -> API, copy the Fire URL, and generate the token (shown once). Save them as repo secrets `BOWL_ROUTINE_FIRE_URL` and `BOWL_ROUTINE_FIRE_TOKEN`. Until then the workflow logs a notice and does nothing.

## Stops

When the routine stops on a PLACEHOLDER banner, a `gm_turn.py` / `agent_turn.py` / `claude` failure, or a commissioner block the apply would still carry out, it writes one `to-commish` file with the date, the intended job, the step, and the one-line reason. It commits and pushes only that file:

`ops <date>: STOPPED <reason>`

No league state and no partial week files. The rule against committing partial week work stays. The note is filed `status: open` and `priority: urgent`. After telling Nick, the Commissioner sets that note to `done`.

## What this is not

Not league state. Scripts do not read it. It does not score, apply FAAB, or change a roster. Celebrity GMs do not read or write it. The Commissioner reads `to-commish/` and tells Nick.

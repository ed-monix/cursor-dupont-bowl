# Grok Bots — DuPont Bowl

**Status (2026-10-15): optional path, not running.** No Grok Commissioner
Bot and no celebrity GM Bots are running. The league runs from the
`bowl_league_ops` Claude routine (`routines/bowl_league_ops.md`), and every
GM turn, the owned two (Ed Monix and Tony Soprano) included, goes through
`scripts/gm_turn.py`, an isolated `claude -p` per team. Nobody runs the
owned teams in Cursor. The Bots below are the gateway path
(`grok_bots.py dispatch`), usable only from a by-hand session while Nick's
local Grok gateway is running; a cloud routine cannot reach it.

On that path: the **Commissioner** clones the league repo, runs the daily
slate, wakes the other Bots, verifies their JSON, and commits. That is the
git gate. Celebrity GMs, Scout, and Media **never** git. They reply to the
Commissioner. The owned two never go on the Bot computer.

Shared computer: GMs must not open `teams/*/general-manager.md` for another
team. Packs are one slug per chat.

## Clock (gateway path, not running)

```text
daily-slate — Commissioner — every day 09:00 America/New_York
  git pull
  python scripts/commish_gate.py daily --write
  ping GMs → ingest replies → commit
```

GMs: one routine `on-commissioner`. Report JSON to the Commissioner.

`python scripts/grok_bots.py routines`

## Commissioner paste

The Commissioner's Grok paste is the block in `skill-commish.pointer.md`
and nothing else; `skill-commish.md` wins over the paste. Each run's first
comment or commit names the file it read:
`read bots/skill-commish.md @ {short sha}` (first body line of a commit),
so a stale paste shows up as an old hash. Added 2026-10-15 (build-out
`docs/plan/2026-10-15-automation-cleanup.md`, "Instructions in git").

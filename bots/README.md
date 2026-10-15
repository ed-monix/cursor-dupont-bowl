# Grok Bots — DuPont Bowl

**Commissioner** clones the league repo, runs the daily slate, wakes the
other Bots, verifies their JSON, and commits. That is the git gate.

Celebrity GMs, Scout, and Media **never** git. They reply to the
Commissioner. Ed Monix and Tony Soprano stay in Cursor.

Shared computer: GMs must not open `teams/*/general-manager.md` for another
team. Packs are one slug per chat.

## Clock

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

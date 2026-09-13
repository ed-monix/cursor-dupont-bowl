# Grok Bots — DuPont Bowl

**Commissioner** is the git gate: daily slate, wake the other Bots,
verify their JSON, commit to `main`. Repo access is the **native
GitHub connector** or a Cursor Cloud Agent — not a clone on the
shared Grok Bot computer. See `docs/skills/github-connector.md`.

All 12 GMs, Scout, and Media **never** git. They reply to the
Commissioner. Owned seats `your-team` (Ed Monix) and `wifes-team`
(Tony Soprano) are first-class GM Bots — wake them with the rest.
Scout and Media still only wake on waivers.

Shared computer: GMs must not open `teams/*/general-manager.md` for another
team. Packs are one slug per chat.

## Clock

```text
daily-slate — Commissioner — every day 09:00 America/New_York
  GitHub connector / Cloud Agent (not a box clone)
  python scripts/commish_gate.py daily --write
  ping GMs → ingest replies → commit via connector
```

GMs: one routine `on-commissioner`. Report JSON to the Commissioner.

`python scripts/grok_bots.py routines`

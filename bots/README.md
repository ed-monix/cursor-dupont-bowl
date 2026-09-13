# Grok Bots — DuPont Bowl

**Commissioner** verifies GM JSON and wakes the other Bots. A
**Cursor Cloud Agent** is the only git writer: daily ops and the
commissioner gate commit and push straight to `main`. Larger
doc/code changes open a PR, then merge. See
`docs/skills/cloud-agents.md`.

Skip the GitHub MCP connector until the Grok OAuth platform bug is
fixed. Never box-computer `gh auth login` or device login. Do not
clone this league onto the shared Grok Bot computer.

All 12 GMs, Scout, and Media never clone and never git. They reply to
the Commissioner. Packs arrive in chat. Owned seats `your-team` (Ed Monix) and `wifes-team`
(Tony Soprano) are first-class GM Bots — wake them with the rest.
Scout and Media still only wake on waivers.

Shared computer: GMs must not open `teams/*/general-manager.md` for another
team. Packs are one slug per chat.

## Clock

```text
daily-slate — Commissioner verifies; Cloud Agent writes git
  every day 09:00 America/New_York
  python scripts/commish_gate.py daily --write
  ping GMs → ingest replies → Cloud Agent commit/push to main
```

GMs: one routine `on-commissioner`. Report JSON to the Commissioner.

`python scripts/grok_bots.py routines`

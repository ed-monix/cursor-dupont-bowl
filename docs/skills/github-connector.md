# Owner rule: GitHub connector only

Required for the whole DuPont Bowl league. Owner overrides any older
"do not connect a GitHub plugin" line.

## Sanctioned path

Grok Bots **always** use the **native GitHub connector** for repository
access. Cursor Cloud Agents that already have that connector are the
same sanctioned path.

## Forbidden as the primary path

- Box-computer GitHub device login
- Local `gh auth login`
- Browser cookie workarounds
- Cloning `ed-monix/cursor-dupont-bowl` onto the shared Grok Bot
  computer for day-to-day ops

## Git gate (unchanged job, new access)

The Commissioner remains the git gate for what may enter `main`
(verify GM JSON, `commish_gate.py ingest`, commit). Access is via the
connector or a Cloud Agent — not a working clone on the shared Bot
disk.

Cloud Agents still run `/apply`, `/recap` follow-up, and
`/refresh-board` after `decisions/` lands.

## Isolation (unchanged)

GMs, Scout, and Media still do not clone and do not browse the repo.
Packs arrive in chat. Tools off. One slug per chat. Never
`state/players.json`, never another team's `general-manager.md` or
`opinions.json`.

All 12 GMs are Grok Bots, including owned seats `your-team` (Ed Monix)
and `wifes-team` (Tony Soprano). Scout and Media still only wake on
waivers.

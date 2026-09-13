# Routines — Cloud Agents write git

**DuPont Commissioner** is the only Bot with a calendar. It verifies
GM JSON. A **Cursor Cloud Agent** is the only git writer: commissioner
gate and daily ops commit and push straight to `main`. All 12 GMs
report to the Commissioner, including owned seats `your-team` (Ed
Monix) and `wifes-team` (Tony Soprano). Scout and Media still only
wake on waivers.

GMs do not clone. Packs arrive in chat. Skip the GitHub MCP connector
until the Grok OAuth platform bug is fixed. Never box-computer
`gh auth login` or device login. See `docs/skills/cloud-agents.md`.

---

## Commissioner — `daily-slate`

**When:** every day 09:00 America/New_York.

**Do:** Cloud Agent has the repo → `python scripts/commish_gate.py daily --write`
→ Cloud Agent commits ops to `main` → ping GMs with packs → ingest
replies → Cloud Agent commits decisions to `main`.

Paste `bots/skill-commish.md`.

---

## Each GM (all 12) — `on-commissioner`

**When:** Commissioner ping. No cron.

**Do:** Reply schema JSON to the Commissioner. Never git.

Paste `bots/skill-gm.md`.

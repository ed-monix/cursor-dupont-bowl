# Routines — Commissioner is the git gate

**DuPont Commissioner** is the only Bot with a calendar and the only Bot
that clones the league repo. All 12 GMs report to the Commissioner,
including owned seats `your-team` (Ed Monix) and `wifes-team` (Tony
Soprano). The Commissioner verifies, then commits. Cursor Cloud Agents
read git after that. Scout and Media still only wake on waivers.

GMs do not clone. Do not give GMs a GitHub plugin.

---

## Commissioner — `daily-slate`

**When:** every day 09:00 America/New_York.

**Do:** pull repo → `python scripts/commish_gate.py daily --write` → commit
ops → ping GMs with packs → ingest replies → commit decisions.

Paste `bots/skill-commish.md`.

---

## Each GM (all 12) — `on-commissioner`

**When:** Commissioner ping. No cron.

**Do:** Reply schema JSON to the Commissioner. Never git.

Paste `bots/skill-gm.md`.

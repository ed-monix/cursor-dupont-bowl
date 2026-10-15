# Routines — Commissioner is the git gate

**Status (2026-10-15): the routine that runs the league is the Claude
routine `bowl_league_ops`** (`routines/bowl_league_ops.md`, pointer paste
`routines/bowl_league_ops.pointer.md`, daily 08:59 America/New_York). It
runs all 12 GM turns through `scripts/gm_turn.py`, the owned two included.
The Grok routines below (`daily-slate`, `on-commissioner`) are the optional
gateway path and are not running; do not schedule them alongside the
Claude routine, or the day runs twice.

On that gateway path, **DuPont Commissioner** is the only Bot with a
calendar and the only Bot that clones the league repo. Celebrity GMs report
to the Commissioner. The Commissioner verifies, then commits; `/apply`
runs from git after that.

GMs do not clone. Do not give GMs a GitHub plugin.

---

## Commissioner — `daily-slate`

**When:** every day 09:00 America/New_York.

**Do:** pull repo → `python scripts/commish_gate.py daily --write` → commit
ops → ping GMs with packs → ingest replies → commit decisions.

Paste the block in `bots/skill-commish.pointer.md`; it reads
`bots/skill-commish.md` from `main` on every run.

---

## Each celebrity GM — `on-commissioner`

**When:** Commissioner ping. No cron.

**Do:** Reply schema JSON to the Commissioner. Never git.

Paste `bots/skill-gm.md`.

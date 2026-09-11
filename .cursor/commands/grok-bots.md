---
description: Grok Bot roster — commissioner clock, isolation, packs
argument-hint: check|routines|ops --date YYYY-MM-DD
---

# /grok-bots

The **Commissioner** is the only Bot with a calendar. Daily 09:00 ET it
checks `python scripts/daily_ops.py` (public NFL games) and wakes whoever
must act. GMs have no gameday cron. Nothing here requires a Mac.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py routines
python scripts/grok_bots.py ops --date 2026-09-13
python scripts/grok_bots.py profile commissioner
python scripts/daily_ops.py --date 2026-09-13
```

Create once in the Grok Bot app: Commissioner routine `daily-slate`; each
celebrity GM routine `on-commissioner` (see `bots/routines.md`).

Owned teams stay in Cursor. Do not clone this repo onto the shared Bot disk.

---
description: Apply FAAB or lineups after the Commissioner gate
argument-hint: [--dry-run]
---

# /apply — scripts mutate rosters after git has decisions/

The Commissioner verifies JSON and commits `state/weeks/*/decisions/`.
It does **not** run FAAB or write `roster.json`. This command does.

1. `git pull`.
2. Refresh the ops file only when today's is missing. Today is the America/New_York date (the runner is UTC, and a UTC date misses Monday night; `scripts/gameday_sync.py`). If `state/ops/<that date>.json` already exists, do not run `--write`: it would replace the file with an empty `gate` and drop what `scripts/lib/commish_gate.py` recorded. If it is missing, run `python scripts/daily_ops.py --date <that date> --write`. Then read `state/ops/latest.json`. Idle / recap → stop (recap is `/recap`); if this run wrote the ops file, commit it first as `ops YYYY-MM-DD: <action>`. Otherwise the refreshed file rides in this run's commit (step 4). The file went stale from 2026-09-20 while weeks were run outside the Commissioner.
3. Dry-run first, then apply:

```bash
python scripts/apply_gate.py --dry-run
python scripts/apply_gate.py
```

- **waivers** — claims from `decisions/<slug>.json` → `faab.py`
- **lineups-early / lineups-main** — `lineups.py --decisions-dir`

Owned GMs (`your-team`, `wifes-team`) must already have files in
`decisions/` from Cursor. Missing slugs stay unapplied; do not invent JSON.

4. One commit: `week <WW>: waivers` or `week <WW>: lineups-early|lineups-main`.
5. Push. `/refresh-board` is not required; Pages rebuilds on push to `main`.
   Rebuild locally if you want a preview:
   `python scripts/build_viewer.py --season 2026`.

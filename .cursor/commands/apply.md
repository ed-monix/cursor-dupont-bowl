---
description: Apply FAAB or lineups after the Commissioner gate
argument-hint: [--dry-run]
---

# /apply — scripts mutate rosters after git has decisions/

The Commissioner verifies JSON and commits `state/weeks/*/decisions/`.
It does **not** run FAAB or write `roster.json`. This command does.

1. `git pull`.
2. Read `state/ops/latest.json`. Idle / recap → stop (recap is `/recap`).
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

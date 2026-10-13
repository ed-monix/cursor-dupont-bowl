---
description: Grok Bot roster — Commissioner is the git gate
argument-hint: check|routines|ops
---

# /grok-bots

The Commissioner clones this repo daily, writes `state/ops/`, wakes all
12 GM Bots (including `your-team` / Ed Monix and `wifes-team` / Tony
Soprano), ingests their JSON (`commish_gate.py`), and commits. GMs never
git. Scout and Media still only wake on waivers. Cloud Agents `/apply`
after the gate. The board is GitHub Pages.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py routines
python scripts/commish_gate.py daily --date 2026-09-13 --write
```

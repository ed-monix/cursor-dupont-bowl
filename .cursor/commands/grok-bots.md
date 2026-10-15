---
description: Grok Bot roster — Commissioner is the git gate
argument-hint: check|routines|ops
---

# /grok-bots

Optional path, not running as of 2026-10-15: no Grok Commissioner or
celebrity GM Bot is running. The league runs from the `bowl_league_ops`
Claude routine (`routines/bowl_league_ops.md`), with every GM turn through
`scripts/gm_turn.py`. What follows applies only while Nick's local Grok
gateway is running.

The Commissioner clones this repo daily, writes `state/ops/`, wakes GMs,
ingests their JSON (`commish_gate.py`), and commits. GMs never git.
Cloud Agents `/apply` after the gate. The board is GitHub Pages.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py routines
python scripts/commish_gate.py daily --date 2026-09-13 --write
```

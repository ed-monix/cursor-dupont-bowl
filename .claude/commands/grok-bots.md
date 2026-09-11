---
description: Grok Bot roster — Commissioner is the git gate
argument-hint: check|routines|ops
---

# /grok-bots

The Commissioner clones this repo daily, writes `state/ops/`, wakes GMs,
ingests their JSON (`commish_gate.py`), and commits. GMs never git.
Cloud Agents read the repo after the gate.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py routines
python scripts/commish_gate.py daily --date 2026-09-13 --write
```

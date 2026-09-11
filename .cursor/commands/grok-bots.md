---
description: Grok Bot roster — check isolation, print profiles and pack-paste prompts
argument-hint: check|list|profile <id>|run-sheet --week N --run waivers|lineups
---

# /grok-bots

Grok Bots are the GM runtime for the ten celebrity teams plus Scout, Media,
and Commissioner. Owned GMs stay in Cursor. This command does **not** create
Bots (do that in the Grok Bot app) and does **not** clone the repo onto the
shared Bot computer.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py list
python scripts/grok_bots.py profile costanza
python scripts/grok_bots.py run-sheet --week <WW> --run waivers
python scripts/grok_bots.py prompt --week <WW> --run waivers --slug costanza
```

Create each `product: grok_bot` row once (see `bots/README.md`). Paste
`bots/skill-gm.md` (or scout/media/commish) into that Bot. Weekly: paste
`prompt` stdout into the Bot, tools off, save JSON under
`state/weeks/2026-w<WW>/decisions/`. Scripts apply (`faab.py`, `lineups.py`).

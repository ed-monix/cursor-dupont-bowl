---
description: Grok Bot roster — isolation check, ensure, one-command dispatch
argument-hint: check|ensure|dispatch --week N --kind waivers|lineups
---

# /grok-bots

Grok Bots are the GM runtime for the ten celebrity teams plus Scout, Media,
and Commissioner. Owned GMs stay in Cursor. Do **not** clone the repo onto
the shared Bot computer. Do **not** paste packs into 12 chats.

The weekly clock is **dispatch**. One command builds isolated packs and
POSTs them through the Grok Bot desktop gateway (`sendPrompt`). Replies
land in `state/weeks/2026-w<WW>/decisions/`. Then `faab.py` / `lineups.py`.

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py list
python scripts/grok_bots.py profile costanza
python scripts/grok_bots.py ensure
python scripts/grok_bots.py dispatch --week <WW> --kind waivers
python scripts/grok_bots.py dispatch --week <WW> --kind lineups --window early
python scripts/grok_bots.py dispatch --week <WW> --kind trades --slug <target> --offer offer.json
```

Gateway (Mac running the Grok Bot app): `GROKBOT_GATEWAY_URL` +
`SAND_GATEWAY_TOKEN`, or `sand-data/gateway.json`. Without it, `dispatch`
and `ensure` print enablement and exit 2.

Owned teams (`your-team`, `wifes-team`) are never dispatched. Use
`prompt` for those Cursor turns only. `prompt` for celebrity GMs is a
debug dump, not the weekly workflow.
